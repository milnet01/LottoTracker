package za.co.antsprojectshub.lottotracker

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
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
 *  The server listens only while the page is on screen: started in onStart,
 *  stopped in onStop, on a fresh port and token each time. The token reaches
 *  the server as the lotto_token cookie, which no other app can read.
 *  Every Python call runs off the main thread. */
class MainActivity : Activity() {
    private lateinit var web: WebView

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

    override fun onStop() {
        super.onStop()
        lifecycle.execute { Py.entry(this).callAttr("stop_server") }
    }

    override fun onDestroy() {
        lifecycle.shutdown()
        actions.shutdown()
        web.destroy()
        super.onDestroy()
    }

    /** Import the inbox, then start the server: the first build reads what was
     *  just imported (§4.2). start_server() stops any server already running. */
    private fun open() {
        lifecycle.execute {
            SmsReader.importNew(this)
            val started = Py.entry(this).callAttr("start_server").asList()
            val port = started[0].toInt()
            val token = started[1].toString()
            runOnUiThread { show(port, token) }
        }
    }

    private fun show(port: Int, token: String) {
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
        if (SmsReader.allowed(this)) open()
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
