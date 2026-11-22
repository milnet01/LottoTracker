package za.co.antsprojectshub.lottotracker

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build

/** Posts android_entry.evening()'s notices, one notification each (§4.6).
 *
 *  Every notification carries a public version naming no game and no date,
 *  so the lock screen shows nothing of a ticket. The text itself is Python's:
 *  this file adds none. */
object Notices {
    private const val CHANNEL = "ticket_warnings"

    fun post(context: Context, notices: List<String>) {
        if (notices.isEmpty()) return
        val manager = context.getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 26) {
            manager.createNotificationChannel(NotificationChannel(
                CHANNEL, context.getString(R.string.channel_name),
                NotificationManager.IMPORTANCE_DEFAULT))
        }
        if (Build.VERSION.SDK_INT >= 33 &&
            context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
                PackageManager.PERMISSION_GRANTED) return
        val open = PendingIntent.getActivity(
            context, 0, Intent(context, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE)
        val title = context.getString(R.string.app_name)
        for (text in notices) {
            val public = builder(context)
                .setContentTitle(title)
                .setContentText(context.getString(R.string.notice_public))
                .build()
            val full = builder(context)
                .setContentTitle(title)
                .setContentText(text)
                .setStyle(Notification.BigTextStyle().bigText(text))
                .setVisibility(Notification.VISIBILITY_PRIVATE)
                .setPublicVersion(public)
                .setContentIntent(open)
                .setAutoCancel(true)
                .build()
            // The same notice replaces itself rather than stacking.
            manager.notify(text.hashCode(), full)
        }
    }

    private fun builder(context: Context): Notification.Builder {
        val b = if (Build.VERSION.SDK_INT >= 26) Notification.Builder(context, CHANNEL)
                else @Suppress("DEPRECATION") Notification.Builder(context)
        return b.setSmallIcon(R.drawable.ic_notice)
    }
}
