Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\nanna\Desktop\ikea_csv"

' Start Streamlit hidden
WshShell.Run "cmd /c python -m streamlit run app.py --server.headless true --server.port 8501", 0, False

' Open browser
WshShell.Run "cmd /c start http://localhost:8501", 0, False
