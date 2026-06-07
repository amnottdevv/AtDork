
# 🔍 Dork Scanner (DuckDuckGo Based)

Tool OSINT sederhana untuk mencari informasi melalui mesin pencari DuckDuckGo menggunakan teknik Google Dorking.

## 📌 Fitur

- Mencari file sensitif, direktori terbuka, admin panel, dll.
- Tampilan tabel rapi dengan `rich`
- Banner ASCII art dengan `pyfiglet`
- Hasil bisa disimpan ke file `.txt`

## 🛠️ Instalasi

1. **Clone atau download** repository ini.
2. **Install dependencies**:

```bash
pip install -r requirements.txt
```

## 🚀 Cara Penggunaan

Jalankan script:

```bash
python main.py
```

Kemudian:
- Masukkan keyword/dork yang ingin dicari.
- Masukkan jumlah maksimal hasil (default 20).
- Lihat hasil di tabel.
- Pilih simpan (y/n) jika ingin menyimpan ke file.

## 📝 Contoh Dork

```bash
intitle:"index of" "backup"
filetype:env "DB_PASSWORD"
inurl:admin login
site:.go.id filetype:pdf "confidential"
```

## ⚠️ Peringatan

*Resiko tanggung sendiri jangan sampai mempermasalhkan dev*

## 👨‍💻 Developed by

**alzzmarket**  
GitHub: [amnottdevv/dork-scanners](https://github.com/amnottdevv/dork-scanners)

---

📄 Lisensi: MIT
