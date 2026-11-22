package za.co.antsprojectshub.lottotracker

import android.content.Context
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequest
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import java.util.concurrent.TimeUnit

/** The evening job (LOTTO-0106 §4.6): import the inbox, then post whatever
 *  android_entry.evening() returns. WorkManager may run it late; accepted. */
class EveningWorker(context: Context, params: WorkerParameters) : Worker(context, params) {
    override fun doWork(): Result {
        SmsReader.importNew(applicationContext)
        val notices = Py.entry(applicationContext).callAttr("evening")
            .asList().map { it.toString() }
        Notices.post(applicationContext, notices)
        return Result.success()
    }

    companion object {
        /** Off the main thread: it asks Python for the first delay. KEEP leaves
         *  an existing schedule alone, so each open does not move it. */
        fun schedule(context: Context) {
            val delay = Py.entry(context).callAttr("next_evening_ms").toLong()
            val request = PeriodicWorkRequest.Builder(
                EveningWorker::class.java, 24, TimeUnit.HOURS)
                .setInitialDelay(delay, TimeUnit.MILLISECONDS)
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                "evening", ExistingPeriodicWorkPolicy.KEEP, request)
        }
    }
}
