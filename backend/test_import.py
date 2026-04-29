import traceback
try:
    import main
    print("SUCCESS")
except Exception as e:
    with open("err.txt", "w", encoding="utf-8") as f:
        f.write(traceback.format_exc())
        print("Wrote to err.txt")
