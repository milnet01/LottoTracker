package za.co.antsprojectshub.lottotracker

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.os.Build
import android.os.Bundle
import android.view.Menu
import android.view.MenuItem
import android.webkit.CookieManager
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/** The page, in a WebView, from the app's own loopback server (LOTTO-0106 §4.4).
 *
 *  The server starts on the first onStart, on a fresh port and token, and
 *  runs until the app's process ends, so switching away and back keeps the
 *  page as it was. Every route needs the token, which reaches the server as
 *  the lotto_token cookie that no other app can read. On a return,
 *  android_entry.resume() decides whether to rebuild in the background.
 *  Every Python call runs off the main thread. */
class MainActivity : Activity() {
    private lateinit var web: WebView
    // The port this activity's WebView has loaded, or 0 before the first.
    private var shownPort = 0

    // Opening and closing run in order on one thread; a slow menu action
    // (Fetch older results waits for its download) runs on another, so it
    // never holds up stopping the server.
    private val lifecycle: ExecutorService = Executors.newSingleThreadExecutor()
    private val actions: ExecutorService = Executors.newSingleThreadExecutor()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        web = WebView(this)
        web.settings.javaScriptEnabled = true  // the page's buttons post with XHR
        web.webViewClient = object : WebViewClient() {
            // The app's own page stays here; any other link opens in the browser.
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                if (request.url.host == "127.0.0.1") return false
                startActivity(Intent(Intent.ACTION_VIEW, request.url))
                return true
            }
        }
        web.loadData(getString(R.string.starting), "text/plain; charset=utf-8", null)
        setContentView(web)
        askPermissions()
        lifecycle.execute { EveningWorker.schedule(this) }
    }

    override fun onStart() {
        super.onStart()
        open()
    }

    override fun onDestroy() {
        // The server is left running: the next activity in this process finds
        // it through resume(), and it ends with the process.
        lifecycle.shutdown()
        actions.shutdown()
        web.destroy()
        super.onDestroy()
    }

    /** Import the inbox, then resume the running server or start one: the
     *  first build reads what was just imported (§4.2). A page already on
     *  screen is kept; when resume() started a rebuild, the page's own poll()
     *  reloads it once the rebuild is done. `fresh` starts a new server and
     *  build whatever the network: the page built before SMS was allowed
     *  holds no tickets. */
    private fun open(fresh: Boolean = false) {
        lifecycle.execute {
            val written = SmsReader.importNew(this)
            val entry = Py.entry(this)
            val resumed = if (fresh) null else entry.callAttr("resume", written, metered())
            if (resumed == null) {
                val started = entry.callAttr("start_server").asList()
                val port = started[0].toInt()
                val token = started[1].toString()
                runOnUiThread { show(port, token) }
                return@execute
            }
            val r = resumed.asList()
            val port = r[0].toInt()
            val token = r[1].toString()
            val rebuilding = r[2].toBoolean()
            runOnUiThread {
                if (shownPort != port) show(port, token)
                else if (rebuilding) web.evaluateJavascript("poll()", null)
            }
        }
    }

    /** Android's word on the network: mobile data, or a hotspot, is metered. */
    private fun metered(): Boolean =
        getSystemService(ConnectivityManager::class.java).isActiveNetworkMetered

    private fun show(port: Int, token: String) {
        shownPort = port
        val url = "http://127.0.0.1:$port/"
        val cookies = CookieManager.getInstance()
        cookies.setCookie(url, "lotto_token=$token; Path=/; HttpOnly; SameSite=Strict") {
            cookies.flush()
            web.loadUrl(url)
        }
    }

    private fun askPermissions() {
        val wanted = mutableListOf(Manifest.permission.READ_SMS)
        if (Build.VERSION.SDK_INT >= 33) wanted.add(Manifest.permission.POST_NOTIFICATIONS)
        val missing = wanted.filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
        if (missing.isNotEmpty()) requestPermissions(missing.toTypedArray(), 1)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>,
                                            grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        // SMS allowed just now: import and rebuild, so the page shows the tickets.
        if (SmsReader.allowed(this)) open(fresh = true)
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menu.add(Menu.NONE, MENU_REFRESH, Menu.NONE, R.string.menu_refresh)
        menu.add(Menu.NONE, MENU_FETCH_OLDER, Menu.NONE, R.string.menu_fetch_older)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        val call = when (item.itemId) {
            MENU_REFRESH -> "refresh"
            MENU_FETCH_OLDER -> {
                Toast.makeText(this, R.string.fetch_older_running, Toast.LENGTH_SHORT).show()
                "fetch_older"
            }
            else -> return super.onOptionsItemSelected(item)
        }
        actions.execute {
            val message = Py.entry(this).callAttr(call).toString()
            runOnUiThread {
                Toast.makeText(this, message, Toast.LENGTH_LONG).show()
                web.reload()
            }
        }
        return true
    }

    private companion object {
        const val MENU_REFRESH = 1
        const val MENU_FETCH_OLDER = 2
    }
}
