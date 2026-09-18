package com.sflms.fcmtest

import android.content.Context

object ReceivedMessageStore {
    private const val PREFERENCES = "safe_message_state"
    private const val LAST_MESSAGE = "last_message"

    fun save(context: Context, eventType: String?, severity: String?) {
        val safeEvent = eventType?.take(64)?.filter { it.isLetterOrDigit() || it == '_' } ?: "unknown"
        val safeSeverity = severity?.take(16)?.filter { it.isLetter() } ?: "unknown"
        val summary = "Received security event: $safeEvent ($safeSeverity)"
        context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
            .edit()
            .putString(LAST_MESSAGE, summary)
            .apply()
    }

    fun last(context: Context): String =
        context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)
            .getString(LAST_MESSAGE, "No message received yet")
            ?: "No message received yet"
}
