// Tang AV Scaler: the board's app (the web page's equal, over Wi-Fi or Bluetooth). AGP 9 compiles the
// Kotlin itself; the Compose compiler is Kotlin's plugin.
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
}

// The release's signing key: never in the repository.  The release workflow (.github/workflows/
// android.yml) writes it from the repository's secrets and names it here; without it a release
// build comes out unsigned (a local check that it builds).
val keystore = System.getenv("TANGAV_KEYSTORE")?.let { file(it) }?.takeIf { it.exists() }

// The version: from the release's tag (app-v1.2.3 -> 1.2.3) and the workflow's run number; a local
// build is 0.0-dev.
val tag = System.getenv("TANGAV_VERSION")?.removePrefix("app-v")
val build = System.getenv("TANGAV_BUILD")?.toIntOrNull() ?: 1

android {
    namespace = "io.github.bryfur.tangav"
    compileSdk = 37
    defaultConfig {
        applicationId = "io.github.bryfur.tangav"
        minSdk = 29                 // (BluetoothDevice.createL2capChannel)
        targetSdk = 37
        versionCode = build
        versionName = tag ?: "0.0-dev"
    }
    signingConfigs {
        if (keystore != null) create("release") {
            storeFile = keystore
            storePassword = System.getenv("TANGAV_STORE_PASSWORD")
            keyAlias = System.getenv("TANGAV_KEY_ALIAS")
            keyPassword = System.getenv("TANGAV_KEY_PASSWORD")
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
            if (keystore != null) signingConfig = signingConfigs.getByName("release")
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
