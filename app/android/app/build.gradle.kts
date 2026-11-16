// Tang AV Scaler: the board's app (the web page's equal, over Wi-Fi or Bluetooth). AGP 9 compiles the
// Kotlin itself; the Compose compiler is Kotlin's plugin.
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "io.github.bryfur.tangav"
    compileSdk = 37
    defaultConfig {
        applicationId = "io.github.bryfur.tangav"
        minSdk = 29                 // (BluetoothDevice.createL2capChannel)
        targetSdk = 37
        versionCode = 1
        versionName = "0.1"
    }
    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
        }
    }
    buildFeatures { compose = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_21
        targetCompatibility = JavaVersion.VERSION_21
    }
}

kotlin { jvmToolchain(21) }

dependencies {
    val bom = platform("androidx.compose:compose-bom:2026.09.00")
    implementation(bom)
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.11.0")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.11.0")
    implementation("androidx.core:core-ktx:1.19.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.11.0")
    debugImplementation("androidx.compose.ui:ui-tooling")
}
