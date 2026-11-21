"""The run tool's environment and output: the app's Android/Kotlin toolchain on PATH, PowerShell 5.1 error-record
noise removed, and system_info naming the toolchain (a model reported "no Gradle, no Kotlin" because it was not on
PATH)."""
import os
from pathlib import Path

from app.tools import mobile, sysinfo
from app.tools.shell_tools import tidy_ps_errors

JAVA_OUT = """[stderr] java : openjdk version "21.0.13" 2026-10-20 LTS
[stderr] At E:\\x\\.session\\scripts\\dc384257a6fa.ps1:23 char:1
[stderr] + java -version 2>&1; echo "---"
[stderr] + ~~~~~~~~~~~~~~~~~~
[stderr]     + CategoryInfo          : NotSpecified: (openjdk version "21.0.13" 2026-10-20 LTS:String) [], RemoteException
[stderr]     + FullyQualifiedErrorId : NativeCommandError
[stderr]
[stderr] OpenJDK Runtime Environment Temurin-21.0.13+9 (build 21.0.13+9-LTS)
---
[stderr] kotlin : The term 'kotlin' is not recognized as the name of a cmdlet, function, script file, or operable program. Check
[stderr]  the spelling of the name, or if a path was included, verify that the path is correct and try again.
[stderr] At E:\\x\\.session\\scripts\\dc384257a6fa.ps1:23 char:33
[stderr] + java -version 2>&1; echo "---"; kotlin -version 2>&1
[stderr] +                                 ~~~~~~
[stderr]     + CategoryInfo          : ObjectNotFound: (kotlin:String) [], CommandNotFoundException
[stderr]     + FullyQualifiedErrorId : CommandNotFoundException
[stderr]
kotlin komutu bulunamadi"""


def test_tidy_ps_errors_keeps_program_text_and_messages():
    out = tidy_ps_errors(JAVA_OUT)
    assert '[stderr] openjdk version "21.0.13" 2026-10-20 LTS' in out
    assert "OpenJDK Runtime Environment" in out
    assert "CategoryInfo" not in out and "FullyQualifiedErrorId" not in out and "char:" not in out
    assert "kotlin : The term 'kotlin' is not recognized" in out  # a real error keeps its message
    assert "kotlin komutu bulunamadi" in out


def test_tidy_ps_errors_leaves_other_output_alone():
    text = "line 1\n[stderr] warning: x\nline + 2"
    assert tidy_ps_errors(text) == text


def test_run_env_appends_toolchain(tmp_path, monkeypatch):
    sdk = tmp_path / "android-sdk"
    for d in ("platform-tools", "emulator", "cmdline-tools/latest/bin"):
        (sdk / d).mkdir(parents=True)
    gradle = tmp_path / "gradle-8.13" / "bin"
    gradle.mkdir(parents=True)
    jdk = tmp_path / "jdk"
    (jdk / "bin").mkdir(parents=True)
    monkeypatch.setattr(mobile, "sdk_root", lambda: sdk)
    monkeypatch.setattr(mobile, "gradle_bin", lambda: str(gradle / "gradle.bat"))
    monkeypatch.setattr(mobile, "java_home", lambda: jdk)
    env = {"PATH": "C:\\mine", "JAVA_HOME": "C:\\myjdk"}
    mobile.add_to_run_env(env)
    parts = env["PATH"].split(os.pathsep)
    assert parts[0] == "C:\\mine"  # the user's own PATH comes first
    assert str(gradle) in parts and str(sdk / "platform-tools") in parts and str(jdk / "bin") in parts
    assert env["ANDROID_HOME"] == str(sdk) and env["JAVA_HOME"] == "C:\\myjdk"  # an existing JAVA_HOME stays
    mobile.add_to_run_env(env)
    assert env["PATH"].split(os.pathsep).count(str(gradle)) == 1  # never added twice


def test_system_info_names_the_toolchain(tmp_path, monkeypatch):
    monkeypatch.setattr(mobile, "sdk_root", lambda: tmp_path / "none")
    monkeypatch.setattr(mobile, "gradle_bin", lambda: None)
    assert "mobile_env action=setup" in sysinfo._mobile_summary()
    sdk = tmp_path / "sdk"
    (sdk / "platforms" / "android-36").mkdir(parents=True)
    monkeypatch.setattr(mobile, "sdk_root", lambda: sdk)
    monkeypatch.setattr(mobile, "gradle_bin", lambda: "G:/gradle-8.13/bin/gradle.bat")
    monkeypatch.setattr(mobile, "java_home", lambda: Path("J:/jdk"))
    s = sysinfo._mobile_summary()
    assert s["platforms"] == ["android-36"] and s["gradle"].endswith("gradle.bat")
    assert "Kotlin Gradle plugin" in s["kotlin"] and "run tool adds them" in s["note"]
