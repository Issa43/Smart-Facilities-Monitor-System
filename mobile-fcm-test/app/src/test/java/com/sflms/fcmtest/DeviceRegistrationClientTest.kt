package com.sflms.fcmtest

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class DeviceRegistrationClientTest {
    @Test
    fun buildsExistingSflmsDeviceEndpoint() {
        assertEquals(
            "http://127.0.0.1:8000/api/v1/notifications/devices/",
            DeviceRegistrationClient.endpoint("http://127.0.0.1:8000/").toString(),
        )
    }

    @Test
    fun rejectsNonLoopbackCleartextEndpoint() {
        assertThrows(IllegalArgumentException::class.java) {
            DeviceRegistrationClient.endpoint("http://192.168.1.50:8000")
        }
    }

    @Test
    fun acceptsHttpsEndpoint() {
        assertEquals(
            "https://example.test/api/v1/notifications/devices/",
            DeviceRegistrationClient.endpoint("https://example.test").toString(),
        )
    }
}
