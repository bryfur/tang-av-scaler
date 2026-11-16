package io.github.bryfur.tangav

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import io.github.bryfur.tangav.model.BoardModel
import io.github.bryfur.tangav.ui.App
import io.github.bryfur.tangav.ui.TangTheme

class MainActivity : ComponentActivity() {
    private val vm: BoardModel by viewModels()
    private val bluetooth = arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
    /** (asked for together: Bluetooth's, and on Android 17 the local network's) */
    private val wanted = if (Build.VERSION.SDK_INT >= 37) bluetooth + "android.permission.ACCESS_LOCAL_NETWORK" else bluetooth
    private var asked = false
    private val ask = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { vm.start(allowed()) }

    private fun allowed() = bluetooth.all { checkSelfPermission(it) == PackageManager.PERMISSION_GRANTED }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { TangTheme { App(vm) } }
    }

    /** Looking for the board and asking it for its state only while the app is on screen. */
    override fun onStart() {
        super.onStart()
        if (wanted.any { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED } && !asked) {
            asked = true
            ask.launch(wanted)          // (the answer starts the rest; Wi-Fi alone works without Bluetooth's)
        } else vm.start(allowed())
    }

    override fun onStop() {
        vm.stop()
        super.onStop()
    }
}
