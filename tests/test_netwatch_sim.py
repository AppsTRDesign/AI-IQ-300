"""AIIQ_NET_SIM only forces "offline" while its file exists; without the file the real connection is probed (a real
outage during an evaluation was taken for "online" and two tasks ended)."""
from app import netwatch


def test_sim_file_forces_offline(tmp_path, monkeypatch):
    sim = tmp_path / "net_down"
    monkeypatch.setenv("AIIQ_NET_SIM", str(sim))
    sim.write_text("1")
    assert netwatch.probe() is False


def test_without_the_file_the_real_probe_decides(tmp_path, monkeypatch):
    monkeypatch.setenv("AIIQ_NET_SIM", str(tmp_path / "net_down"))
    monkeypatch.setenv("AIIQ_NETWATCH", "1")
    monkeypatch.setattr(netwatch, "_proxy", lambda: None)

    def no_dns(*a, **k):
        raise OSError("getaddrinfo failed")
    monkeypatch.setattr(netwatch.socket, "getaddrinfo", no_dns)
    assert netwatch.probe() is False  # used to say True: the missing sim file meant "online"
