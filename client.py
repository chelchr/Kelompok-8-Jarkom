import math
import random
import socket
import sys
from fractions import Fraction

import protocol

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 12000

SERVICE_NAMES = {
    protocol.SERVICE_COUNT_CHAR: "Hitung jumlah karakter",
    protocol.SERVICE_COUNT_WORD: "Hitung jumlah kata",
    protocol.SERVICE_REVERSE_STRING: "Balik string",
    protocol.SERVICE_REMOVE_VOWEL: "Hapus huruf vokal",
    protocol.SERVICE_MATRIX_DET_INV: "Determinan & invers matriks 3x3",
}

MENU_ORDER = protocol.ALL_SERVICES  # menu 1..5 sesuai urutan ini
VOWELS = set("aeiouAEIOU")

# status layanan menurut pengetahuan klien (hanya bertambah, tidak pernah aktif lagi)
disabled_services = set()


class ServerShutdown(Exception):
    pass


class ConnectionClosed(Exception):
    pass


# ---------------------------------------------------------------------------
# Perhitungan lokal untuk memverifikasi jawaban server
# ---------------------------------------------------------------------------
def expected_text_result(service, text):
    if service == protocol.SERVICE_COUNT_CHAR:
        return len(text)
    if service == protocol.SERVICE_COUNT_WORD:
        return len(text.split())
    if service == protocol.SERVICE_REVERSE_STRING:
        return text[::-1]
    if service == protocol.SERVICE_REMOVE_VOWEL:
        return "".join(ch for ch in text if ch not in VOWELS)
    raise ValueError("Layanan teks tidak dikenal")


def matrix_det_inv_exact(m):
    """Hitung determinan dan invers dengan Fraction agar tepat."""
    f = [[Fraction(str(v)) for v in row] for row in m]
    (a, b, c), (d, e, g), (h, i, j) = f
    det = a * (e * j - g * i) - b * (d * j - g * h) + c * (d * i - e * h)
    if det == 0:
        return det, None
    cof = [
        [e * j - g * i, -(d * j - g * h), d * i - e * h],
        [-(b * j - c * i), a * j - c * h, -(a * i - b * h)],
        [b * g - c * e, -(a * g - c * d), a * e - b * d],
    ]
    inv = [[cof[col][row] / det for col in range(3)] for row in range(3)]
    return det, inv


def is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def verify_matrix(payload, result):
    """Kembalikan (benar: bool, alasan: str)."""
    if not isinstance(result, dict):
        return False, "result bukan objek"
    det, inv = matrix_det_inv_exact(payload)

    srv_det = result.get("determinant")
    if not is_number(srv_det):
        return False, "determinant bukan angka"
    if not math.isclose(float(det), float(srv_det), rel_tol=1e-9, abs_tol=1e-6):
        return False, f"determinan seharusnya {float(det):g}, server mengirim {srv_det}"

    srv_inv = result.get("inverse")
    if inv is None:
        if srv_inv is not None:
            return False, "matriks singular, invers seharusnya null"
        return True, ""
    if (not isinstance(srv_inv, list) or len(srv_inv) != 3
            or any(not isinstance(r, list) or len(r) != 3 for r in srv_inv)
            or any(not is_number(v) for r in srv_inv for v in r)):
        return False, "format invers tidak valid"
    for r in range(3):
        for c in range(3):
            # server membulatkan 4 desimal, jadi beri toleransi
            if abs(float(inv[r][c]) - srv_inv[r][c]) > 1e-3:
                return False, f"invers[{r}][{c}] seharusnya {float(inv[r][c]):.4f}, server mengirim {srv_inv[r][c]}"
    return True, ""


def verify_result(service, payload, result):
    if service == protocol.SERVICE_MATRIX_DET_INV:
        return verify_matrix(payload, result)
    expected = expected_text_result(service, payload)
    if result == expected and type(result) is type(expected):
        return True, ""
    return False, f"seharusnya {expected!r}, server mengirim {result!r}"


# ---------------------------------------------------------------------------
# Komunikasi
# ---------------------------------------------------------------------------
def recv(rfile):
    """Baca satu pesan. SERVER_SHUTDOWN dan koneksi putus dijadikan exception."""
    try:
        msg = protocol.read_message(rfile)
    except ValueError:
        print("[!] Server mengirim pesan yang bukan JSON valid.")
        return {}
    if msg is None:
        raise ConnectionClosed()
    if msg.get("msg_type") == protocol.MSG_SERVER_SHUTDOWN:
        print(f"[SERVER] {msg.get('message', 'Server berhenti.')}")
        raise ServerShutdown()
    return msg


def mark_disabled(service):
    disabled_services.add(service)


def request_service(rfile, wfile, service, payload):
    protocol.send_message(wfile, {
        "msg_type": protocol.MSG_REQUEST,
        "service": service,
        "payload": payload,
    })
    print(f"[KIRIM] REQUEST {service}: {payload!r}")

    msg = recv(rfile)
    mtype = msg.get("msg_type")

    if mtype == protocol.MSG_ERROR:
        print(f"[ERROR dari server] {msg.get('message')}")
        return

    if mtype != protocol.MSG_RESPONSE:
        print(f"[!] Pesan tidak terduga: {msg}")
        return

    status = msg.get("status")
    if status == protocol.STATUS_SERVICE_DISABLED:
        mark_disabled(service)
        print(f"[INFO] {msg.get('message', 'Layanan tidak aktif.')}")
        return
    if status != protocol.STATUS_OK:
        print(f"[!] Status tidak dikenal: {status}")
        return

    result = msg.get("result")
    print(f"[TERIMA] RESPONSE hasil dari server: {result!r}")

    correct, reason = verify_result(service, payload, result)
    ack_status = protocol.STATUS_CORRECT if correct else protocol.STATUS_INCORRECT
    if correct:
        print("[CEK] Hasil BENAR -> kirim ACK CORRECT")
    else:
        print(f"[CEK] Hasil SALAH ({reason}) -> kirim ACK INCORRECT")

    protocol.send_message(wfile, {
        "msg_type": protocol.MSG_ACK,
        "service": service,
        "status": ack_status,
    })

    if correct:
        return  # server tidak membalas ACK CORRECT

    # ACK INCORRECT: server akan mengirim SERVICE_DISABLED_NOTICE
    notice = recv(rfile)
    if notice.get("msg_type") == protocol.MSG_SERVICE_DISABLED_NOTICE:
        mark_disabled(notice.get("service", service))
        print(f"[SERVER] {notice.get('message')}")
    else:
        print(f"[!] Pesan tidak terduga setelah ACK: {notice}")
        return

    # bila semua layanan nonaktif, server langsung mengirim SERVER_SHUTDOWN
    if len(disabled_services) == len(protocol.ALL_SERVICES):
        recv(rfile)  # akan melempar ServerShutdown


# ---------------------------------------------------------------------------
# Input pengguna
# ---------------------------------------------------------------------------
def read_matrix():
    print("Masukkan matriks 3x3, tiap baris 3 angka dipisah spasi.")
    matrix = []
    for r in range(1, 4):
        while True:
            parts = input(f"  Baris {r}: ").split()
            try:
                if len(parts) != 3:
                    raise ValueError
                row = []
                for p in parts:
                    v = float(p)
                    row.append(int(v) if v.is_integer() else v)
                matrix.append(row)
                break
            except ValueError:
                print("  Harus tepat 3 angka. Coba lagi.")
    return matrix


def show_menu():
    print("\n=== MENU ===")
    for idx, svc in enumerate(MENU_ORDER, start=1):
        mark = "  [NONAKTIF]" if svc in disabled_services else ""
        print(f"{idx}. {SERVICE_NAMES[svc]} ({svc}){mark}")
    print("6. Mode otomatis (demo)")
    print("0. Keluar")


def auto_demo(rfile, wfile):
    samples = {
        protocol.SERVICE_COUNT_CHAR: "Jaringan Komputer",
        protocol.SERVICE_COUNT_WORD: "praktikum jaringan komputer UGM",
        protocol.SERVICE_REVERSE_STRING: "Gadjah Mada",
        protocol.SERVICE_REMOVE_VOWEL: "Universitas Gadjah Mada",
        protocol.SERVICE_MATRIX_DET_INV: [[2, 0, 1], [1, 3, 2], [1, 1, 1]],
    }
    print("\n[DEMO] Mengirim request acak sampai semua layanan nonaktif (Ctrl+C untuk berhenti).")
    while True:
        active = [s for s in protocol.ALL_SERVICES if s not in disabled_services]
        if not active:
            return
        svc = random.choice(active)
        request_service(rfile, wfile, svc, samples[svc])
        print()


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HOST
    port = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT

    try:
        sock = socket.create_connection((host, port), timeout=10)
    except OSError as e:
        print(f"Gagal terhubung ke {host}:{port} -> {e}")
        return
    sock.settimeout(None)
    rfile = sock.makefile("r", encoding="utf-8")
    wfile = sock.makefile("w", encoding="utf-8")
    print(f"Terhubung ke server {host}:{port}")

    try:
        while True:
            show_menu()
            choice = input("Pilih: ").strip()

            if choice == "0":
                break
            if choice == "6":
                auto_demo(rfile, wfile)
                continue
            if not choice.isdigit() or not (1 <= int(choice) <= len(MENU_ORDER)):
                print("Pilihan tidak valid.")
                continue

            service = MENU_ORDER[int(choice) - 1]
            if service in disabled_services:
                print("Layanan ini sudah dinonaktifkan server.")
                continue

            if service == protocol.SERVICE_MATRIX_DET_INV:
                payload = read_matrix()
            else:
                payload = input("Masukkan teks: ")

            request_service(rfile, wfile, service, payload)
    except ServerShutdown:
        print("Semua layanan nonaktif. Klien berhenti.")
    except ConnectionClosed:
        print("Koneksi ditutup oleh server.")
    except (KeyboardInterrupt, EOFError):
        print("\nKlien dihentikan.")
    except OSError as e:
        print(f"Kesalahan jaringan: {e}")
    finally:
        for f in (rfile, wfile):
            try:
                f.close()
            except OSError:
                pass
        sock.close()
        print("Koneksi ditutup.")


if __name__ == "__main__":
    main()
