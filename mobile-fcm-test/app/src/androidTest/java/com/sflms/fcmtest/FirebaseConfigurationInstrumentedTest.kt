package com.sflms.fcmtest

import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.google.firebase.FirebaseApp
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class FirebaseConfigurationInstrumentedTest {
    @Test
    fun installedAppUsesApprovedFirebaseIdentity() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val app = FirebaseApp.initializeApp(context)
        assertNotNull(app)
        assertEquals("com.sflms.fcmtest", context.packageName)
        assertEquals("sflms-fcm-ese-test", app!!.options.projectId)
        assertEquals(
            "1:783021811135:android:b48678d7c2170e35cc6d0a",
            app.options.applicationId,
        )
    }
}
