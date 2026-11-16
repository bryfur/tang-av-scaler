package io.github.bryfur.tangav.net

import android.annotation.SuppressLint
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothManager
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.os.Build
import android.os.ParcelUuid
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import java.util.concurrent.Executors

/** A board found: on the network (host), over Bluetooth (device), or both. */
data class Found(
    val name: String,
    val host: String? = null,
    val device: BluetoothDevice? = null,
    val rssi: Int? = null,
    val bonded: Boolean = false,
)

/**
 * Finds boards: on the local network by mDNS (_http._tcp with TXT board=tang-av-scaler: the
 * firmware's wifi.c), over Bluetooth LE by the service the board advertises (ble.c), and the boards
 * this phone is already paired with.
 */
@SuppressLint("MissingPermission")
class Discovery(private val ctx: Context) {
    private val _wifi = MutableStateFlow<Map<String, Found>>(emptyMap())
    private val _ble = MutableStateFlow<Map<String, Found>>(emptyMap())
    val wifi: StateFlow<Map<String, Found>> = _wifi
    val ble: StateFlow<Map<String, Found>> = _ble

    private val nsd = ctx.getSystemService(NsdManager::class.java)
    private val bt = ctx.getSystemService(BluetoothManager::class.java)?.adapter
    private var nsdListener: NsdManager.DiscoveryListener? = null
    private var scan: ScanCallback? = null
    private val resolver = Executors.newSingleThreadExecutor()

    val bluetoothThere get() = bt != null
    val bluetoothOn get() = bt?.isEnabled == true

    fun start(withBluetooth: Boolean) {
        startNsd()
        if (withBluetooth) {
            bonded()
            startScan()
        }
    }

    fun stop() {
        nsdListener?.let { try { nsd.stopServiceDiscovery(it) } catch (_: Exception) {} }
        nsdListener = null
        scan?.let { try { bt?.bluetoothLeScanner?.stopScan(it) } catch (_: Exception) {} }
        scan = null
    }

    // ---- the network ----
    private fun startNsd() {
        if (nsdListener != null) return
        val l = object : NsdManager.DiscoveryListener {
            override fun onDiscoveryStarted(t: String) = Unit
            override fun onDiscoveryStopped(t: String) = Unit
            override fun onStartDiscoveryFailed(t: String, e: Int) { nsdListener = null }
            override fun onStopDiscoveryFailed(t: String, e: Int) = Unit
            override fun onServiceFound(s: NsdServiceInfo) = resolve(s)
            override fun onServiceLost(s: NsdServiceInfo) {
                _wifi.update { m -> m.filterValues { it.name != s.serviceName } }
            }
        }
        nsdListener = l
        try { nsd.discoverServices("_http._tcp", NsdManager.PROTOCOL_DNS_SD, l) } catch (_: Exception) { nsdListener = null }
    }

    private fun resolve(s: NsdServiceInfo) {
        if (Build.VERSION.SDK_INT >= 34) {
            val cb = object : NsdManager.ServiceInfoCallback {
                override fun onServiceInfoCallbackRegistrationFailed(e: Int) = Unit
                override fun onServiceUpdated(i: NsdServiceInfo) {
                    found(i)
                    try { nsd.unregisterServiceInfoCallback(this) } catch (_: Exception) {}
                }
                override fun onServiceLost() = Unit
                override fun onServiceInfoCallbackUnregistered() = Unit
            }
            try { nsd.registerServiceInfoCallback(s, resolver, cb) } catch (_: Exception) {}
        } else {
            // (the old resolver takes one at a time)
            resolver.execute {
                val done = java.util.concurrent.CountDownLatch(1)
                @Suppress("DEPRECATION")
                nsd.resolveService(s, object : NsdManager.ResolveListener {
                    override fun onResolveFailed(i: NsdServiceInfo, e: Int) = done.countDown()
                    override fun onServiceResolved(i: NsdServiceInfo) { found(i); done.countDown() }
                })
                done.await(5, java.util.concurrent.TimeUnit.SECONDS)
            }
        }
    }

    private fun found(i: NsdServiceInfo) {
        val board = i.attributes["board"]?.decodeToString()
        if (board != "tang-av-scaler" && !i.serviceName.contains("AV scaler", true) &&
            !i.serviceName.contains("Tang AV", true)) return
        val addr = (if (Build.VERSION.SDK_INT >= 34) i.hostAddresses.firstOrNull() else @Suppress("DEPRECATION") i.host)
            ?.hostAddress ?: return
        if (addr.contains(':')) return          // (an IPv6 link-local address: the IPv4 one will do)
        val host = if (i.port == 80) addr else "$addr:${i.port}"
        _wifi.update { it + (host to Found(i.serviceName, host = host)) }
    }

    // ---- Bluetooth ----
    private fun bonded() {
        val b = bt ?: return
        val found = try {
            b.bondedDevices.filter { (it.name ?: "").contains("Tang AV", true) }
        } catch (_: SecurityException) { emptyList() }
        _ble.update { m -> m + found.associate { it.address to Found(it.name ?: it.address, device = it, bonded = true) } }
    }

    private fun startScan() {
        val s = bt?.bluetoothLeScanner ?: return
        if (scan != null) return
        val cb = object : ScanCallback() {
            override fun onScanResult(type: Int, r: ScanResult) {
                val d = r.device
                val bondedNow = try { d.bondState == BluetoothDevice.BOND_BONDED } catch (_: SecurityException) { false }
                val name = r.scanRecord?.deviceName ?: (try { d.name } catch (_: SecurityException) { null }) ?: "Tang AV Scaler"
                _ble.update { it + (d.address to Found(name, device = d, rssi = r.rssi, bonded = bondedNow)) }
            }
        }
        scan = cb
        try {
            s.startScan(
                listOf(ScanFilter.Builder().setServiceUuid(ParcelUuid(BleTransport.SERVICE)).build()),
                ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build(), cb,
            )
        } catch (_: SecurityException) { scan = null }
    }
}
