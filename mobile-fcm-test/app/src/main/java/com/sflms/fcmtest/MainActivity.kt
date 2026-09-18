package com.sflms.fcmtest

import android.Manifest
import android.app.Activity
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import com.google.firebase.FirebaseApp
import com.google.firebase.messaging.FirebaseMessaging

class MainActivity : Activity() {
    private lateinit var firebaseStatus: TextView
    private lateinit var registrationStatus: TextView
    private lateinit var lastMessage: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        firebaseStatus = findViewById(R.id.firebaseStatus)
        registrationStatus = findViewById(R.id.registrationStatus)
        lastMessage = findViewById(R.id.lastMessage)
        createNotificationChannel()
        requestNotificationPermission()
        initializeFirebase()

        findViewById<Button>(R.id.registerDevice).setOnClickListener {
            registerDevice(
                findViewById<EditText>(R.id.backendUrl).text.toString(),
                findViewById<EditText>(R.id.accessToken).text.toString(),
            )
        }
    }

    override fun onResume() {
        super.onResume()
        if (::lastMessage.isInitialized) {
            lastMessage.text = ReceivedMessageStore.last(this)
        }
    }

    private fun initializeFirebase() {
        if (FirebaseApp.initializeApp(this) == null) {
            firebaseStatus.text = "Firebase configuration unavailable"
            return
        }
        FirebaseMessaging.getInstance().token.addOnCompleteListener { task ->
            if (task.isSuccessful && !task.result.isNullOrBlank()) {
                AppSession.fcmToken = task.result
                firebaseStatus.text = "Firebase ready — FCM token obtained"
            } else {
                firebaseStatus.text = "Firebase initialized, token unavailable"
            }
        }
    }

    private fun registerDevice(baseUrl: String, accessToken: String) {
        val token = AppSession.fcmToken
        if (token.isNullOrBlank()) {
            registrationStatus.text = "Registration blocked: FCM token unavailable"
            return
        }
        registrationStatus.text = "Registering…"
        Thread {
            val result = runCatching {
                DeviceRegistrationClient.register(baseUrl, accessToken, token)
            }
            runOnUiThread {
                registrationStatus.text = when (val status = result.getOrNull()) {
                    200, 201 -> "Device registered through SFLMS"
                    null -> "Registration failed locally"
                    else -> "SFLMS registration failed (HTTP $status)"
                }
            }
        }.start()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            getSystemService(NotificationManager::class.java).createNotificationChannel(
                NotificationChannel(
                    FcmTestMessagingService.CHANNEL_ID,
                    getString(R.string.notification_channel_name),
                    NotificationManager.IMPORTANCE_HIGH,
                ),
            )
        }
    }

    private fun requestNotificationPermission() {
        if (
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1001)
        }
    }
}
