"""Jalankan server SI-KUR:  python run.py   (opsional: python run.py --reset)"""
import sys

import uvicorn

if __name__ == "__main__":
    if "--reset" in sys.argv:
        from app.seed import seed
        seed(verbose=False)
        print("Database demo dibuat ulang.")
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
