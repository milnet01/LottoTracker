package za.co.antsprojectshub.lottotracker

import android.content.Context
import android.system.Os
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File

/** The one door into Python: android_entry.py (LOTTO-0106 §4.2).
 *
 *  Called off the main thread only, by the activity's executors and the
 *  evening worker. The first call starts Python, after pointing paths.DATA
 *  and supervise.config_home() at the app's private storage (§4.3). */
object Py {
    @Synchronized
    fun entry(context: Context): PyObject {
        if (!Python.isStarted()) {
            val files = context.applicationContext.filesDir
            Os.setenv("XDG_DATA_HOME", File(files, "data").path, true)
            Os.setenv("XDG_CONFIG_HOME", File(files, "config").path, true)
            Python.start(AndroidPlatform(context.applicationContext))
        }
        return Python.getInstance().getModule("android_entry")
    }
}
