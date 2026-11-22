// The app module (LOTTO-0106 §4.1, §4.8).
plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

val repo: File = rootDir.parentFile

// versionName is VERSION's text; versionCode is major*10000 + minor*100 + patch,
// so every release is higher than the one before (§4.8).
val versionText: String = repo.resolve("VERSION").readText().trim()
val versionNumber: Int = versionText.split(".").map { it.toInt() }
    .let { (major, minor, patch) -> major * 10000 + minor * 100 + patch }

// The Python the phone runs: an EXPLICIT list, never the repository folder
// (§4.8, INV-124). The working tree holds the real SMS dump and the scraped
// archive, and a folder-wide source set would ship them inside the APK.
// Every project module android_entry.py reaches, function-level imports
// included. find_lotto_sms.py is left out: only watch_sms.connect() imports
// it, and the phone never calls connect().
val pythonSources = listOf(
    "android_entry.py",
    "backfill.py",
    "check.py",
    "clock.py",
    "expiry.py",
    "history.py",
    "page.py",
    "paths.py",
    "results.py",
    "serve.py",
    "supervise.py",
    "tickets.py",
    "watch_sms.py",
    "icons/*.svg",
    "fonts/*",
)
val pythonStage = layout.buildDirectory.dir("python-src")

val stagePython by tasks.registering(Sync::class) {
    from(repo) { include(pythonSources) }
    into(pythonStage)
}
// Chaquopy's merge<Variant>PythonSources tasks read the staged folder.
tasks.matching { it.name.endsWith("PythonSources") }.configureEach { dependsOn(stagePython) }

android {
    namespace = "za.co.antsprojectshub.lottotracker"
    compileSdk = 36

    defaultConfig {
        applicationId = "za.co.antsprojectshub.lottotracker"
        minSdk = 24
        targetSdk = 36
        versionCode = versionNumber
        versionName = versionText
        ndk {
            // Python 3.12 and newer is 64-bit only. x86_64 is for the emulator.
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    // The key lives outside the repository (§4.8): tools/build_apk.sh mounts
    // it and passes its path and password in the environment.
    signingConfigs {
        create("release") {
            val keystore = System.getenv("LOTTO_KEYSTORE")
            if (keystore != null) {
                storeFile = file(keystore)
                storePassword = System.getenv("LOTTO_KEYSTORE_PASSWORD")
                keyAlias = "lottotracker"
                keyPassword = System.getenv("LOTTO_KEYSTORE_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

chaquopy {
    defaultConfig {
        // 3.13 or newer, for sys.platform == "android" (§4.3, PEP 738).
        version = "3.13"
    }
    sourceSets {
        getByName("main") {
            setSrcDirs(listOf(pythonStage.get().asFile))
        }
    }
}

dependencies {
    implementation("androidx.work:work-runtime:2.12.0")
}
