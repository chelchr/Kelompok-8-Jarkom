# Kelompok-8-Jarkom
Nama:
- Chelsea Christofera Antonioli Purnomo (25/558145/PA/23462)
- Ahmad Farhan Hidayat (25/559740/PA/23558)
- Saktyaveshavatar Dharmesthabuddhi (25/566653/PA/23920)
- Gusti Rayna (25/557884/PA/23446)
  
## Bagian Client Aplikasi Jaringan Socket Programming
Implementasi client sesuai `PROTOCOL.md` yang dibangun dengan Python standard library saja (`socket`, `json`, `random`, `math`, `sys`, `fractions`), tidak ada dependency eksternal.

## Struktur File
- `client.py` - Program utama: Koneksi TCP ke server, menu layanan, pengiriman request, pemeriksaan hasil dari server, pengiriman ACK, dan penanganan layanan yang dinonaktifkan.
- `protocol.py` - Konstanta jenis pesan, kode layanan, status, dan fungsi kirim/terima pesan JSON.

## Cara Menjalankan
```bash
python client.py
```

Client akan terhubung ke server pada port `12000`.

## Konfigurasi
- `DEFAULT_HOST` di `client.py` - Alamat server yang digunakan sercara default, yaitu `127.0.0.1`.
- `DEFAULT_PORT` di `client.py` - Port server yang digunakan, yaitu `12000`.
  
## Layanan
Client menyediakan menu untuk menggunakan lima layanan berikut dari server:
1. Hitung jumlah karakter
2. Hitung jumlah kata
3. Balik string
4. Hapus huruf vokal
5. Hitung determinan dan invers matriks 3x3
Selain itu, tersedia mode otomatis (demo) untum mengiirm request secara acak ke layanan yang masih aktif.

## Perilaku
- Client terhubung ke server menggunakan TCP socket.
- Client mengirim `REQUEST` berisi layanan dan data yang ingin diproses.
- Client menerima `RESPONSE` dari server.
- Client menghitung hasil yang seharusnya secara lokal dan membandingkannya dengan hasil dari server.
- Jika hasil benar, client mengirim `ACK` dengan status `CORRECT`.
- Jika hasil salah, client mengirim `ACK` dengan status `INCORRECT`.
- Jika server menonaktifkan suatu layanan, client menerima `SERVICE_DISABLED_NOTICE` dan menandai layanan tersebut sebagai nonaktif.
- Client tidak lagi mengirim request ke layanan yang sudah dinonaktifkan.
- Jika semua layanan telah dinonaktifkan, client menerima `SERVER_SHUTDOWN` dan menghentikan prosesnya.

