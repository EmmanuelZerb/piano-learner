import threading

# Un seul modèle à la fois sur le GPU : 8 Go de VRAM ne suffisent pas pour enchaîner
# en parallèle Demucs et ByteDance, et le CPU ne gagnerait rien non plus.
gpu_lock = threading.Lock()
