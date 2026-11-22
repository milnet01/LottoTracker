package za.co.antsprojectshub.lottotracker

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.provider.Telephony.Sms

/** Moves inbox rows to android_entry.import_messages() (LOTTO-0106 §4.1).
 *
 *  It filters nothing: which messages are wanted is watch_sms.wanted()'s
 *  decision, in Python (INV-129). It asks only for rows newer than
 *  android_entry.since_ms(), which is 0 on the first open. */
object SmsReader {
    fun allowed(context: Context): Boolean =
        context.checkSelfPermission(Manifest.permission.READ_SMS) ==
            PackageManager.PERMISSION_GRANTED

    /** -> how many messages Python wrote; 0 when SMS is not allowed. */
    fun importNew(context: Context): Int {
        if (!allowed(context)) return 0
        val entry = Py.entry(context)
        val since = entry.callAttr("since_ms").toLong()
        val rows = ArrayList<Array<Any>>()
        context.contentResolver.query(
            Sms.Inbox.CONTENT_URI,
            arrayOf(Sms.ADDRESS, Sms.DATE, Sms.BODY),
            "${Sms.DATE} > ?",
            arrayOf(since.toString()),
            "${Sms.DATE} ASC",
        )?.use { cursor ->
            while (cursor.moveToNext()) {
                rows.add(arrayOf(
                    cursor.getString(0) ?: "",
                    cursor.getLong(1),
                    cursor.getString(2) ?: "",
                ))
            }
        }
        return entry.callAttr("import_messages", rows.toTypedArray()).toInt()
    }
}
