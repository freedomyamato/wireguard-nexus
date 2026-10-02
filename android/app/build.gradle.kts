plugins { id("com.android.application") }
android {
    namespace = "org.wgnexus.mobile"
    compileSdk = 36
    defaultConfig {
        applicationId = "org.wgnexus.mobile"
        minSdk = 26
        targetSdk = 36
        versionCode = 2
        versionName = "0.2-private-beta"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
        isCoreLibraryDesugaringEnabled = true
    }
    signingConfigs {
        create("ownerRelease") {
            val path = System.getenv("NEXUS_KEYSTORE")
            if (path != null) {
                storeFile = file(path)
                storePassword = System.getenv("NEXUS_STORE_PASSWORD")
                keyAlias = System.getenv("NEXUS_KEY_ALIAS")
                keyPassword = System.getenv("NEXUS_KEY_PASSWORD")
            }
        }
    }
    buildTypes {
        getByName("release") { signingConfig = signingConfigs.getByName("ownerRelease") }
    }
}
dependencies {
    implementation("com.wireguard.android:tunnel:1.0.20260102")
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.5")
}
