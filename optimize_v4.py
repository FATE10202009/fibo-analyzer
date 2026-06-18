file_path = r"c:\Users\fate1\Desktop\pythonworkspace\coin\streamlit_app.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Normalize line endings
content = content.replace("\r\n", "\n")

start_text = '        if show_virtual_trading:\n            with right_col:'
end_text = '    except Exception as e:\n        st.error(f"❌ 데이터 분석 중 오류가 발생했습니다.")'

start_idx = content.find(start_text)
end_idx = content.find(end_text)

if start_idx != -1 and end_idx != -1:
    before = content[:start_idx]
    after = content[end_idx:]
    
    middle = """        if show_virtual_trading:
            with right_col:
                render_virtual_trading_panel(results)
    """
    
    new_content = before + middle + after
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Successfully replaced virtual trading panel with fragment call!")
else:
    print(f"Failed to find markers! start_idx={start_idx}, end_idx={end_idx}")
