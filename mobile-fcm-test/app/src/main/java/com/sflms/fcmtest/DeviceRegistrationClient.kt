package com.sflms.fcmtest

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL

object DeviceRegistrationClient {
    fun endpoint(baseUrl: String): URL {
        val normalized = baseUrl.trim().trimEnd('/')
        val uri = URI(normalized)
        require(
            uri.scheme == "https" ||
                (uri.scheme == "http" && uri.host in setOf("127.0.0.1", "localhost")),
        ) { "Use HTTPS, or loopback HTTP through ADB reverse." }
        return URI("$normalized/api/v1/notifications/devices/").toURL()
    }

    fun register(baseUrl: String, accessToken: String, fcmToken: String): Int {
        require(accessToken.isNotBlank()) { "A human JWT access token is required." }
        require(fcmToken.isNotBlank()) { "An FCM token is required." }
        val connection = endpoint(baseUrl).openConnection() as HttpURLConnection
        return try {
            connection.requestMethod = "POST"
            connection.connectTimeout = 10_000
            connection.readTimeout = 15_000
            connection.doOutput = true
            connection.setRequestProperty("Authorization", "Bearer $accessToken")
            connection.setRequestProperty("Content-Type", "application/json")
            val payload = JSONObject()
                .put("token", fcmToken)
                .put("platform", "android")
                .toString()
            connection.outputStream.use { output ->
                output.write(payload.toByteArray(Charsets.UTF_8))
            }
            connection.responseCode
        } finally {
            connection.disconnect()
        }
    }
}
