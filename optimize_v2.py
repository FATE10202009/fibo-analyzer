import subprocess

# Revert streamlit_app.py first to clean state
subprocess.run(["git", "checkout", "streamlit_app.py"], cwd=r"c:\Users\fate1\Desktop\pythonworkspace\coin")

file_path = r"c:\Users\fate1\Desktop\pythonworkspace\coin\streamlit_app.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update the JavaScript in the file to handle isCustomKeyboardInput
old_js_bind = """        // 모든 input을 감시하고 포커싱 이벤트 달기
        function checkAndBindInputs() {
            const inputs = doc.querySelectorAll('input[type="text"]');
            inputs.forEach(input => {
                if (input.dataset.vkeyBound) return;
                input.dataset.vkeyBound = "true";

                const handleFocus = () => {
                    if (activeInput !== input) {
                        hangulBuffer = [];
                    }
                    activeInput = input;
                    showKeyboard();  // 항상 포커스 시 키보드 표시
                };

                input.addEventListener('focus', handleFocus);
                input.addEventListener('click', handleFocus);
                input.addEventListener('input', () => {
                    activeInput = input;
                    if (input.value.trim() === "") {
                        showKeyboard();
                    }
                });
            });
        }"""

new_js_bind = """        function isCustomKeyboardInput(input) {
            const placeholder = input.placeholder || "";
            if (placeholder.includes("티커") || 
                placeholder.includes("목표 가격") || 
                placeholder.includes("현재가:") || 
                placeholder.includes("금액을 입력하세요") || 
                placeholder.includes("수량을 입력하세요")) {
                return true;
            }
            return false;
        }

        // 모든 input을 감시하고 포커싱 이벤트 달기
        function checkAndBindInputs() {
            const inputs = doc.querySelectorAll('input[type="text"], input[type="number"]');
            inputs.forEach(input => {
                if (input.dataset.vkeyBound) return;
                input.dataset.vkeyBound = "true";

                if (isCustomKeyboardInput(input)) {
                    input.setAttribute('inputmode', 'none');

                    const handleFocus = () => {
                        if (activeInput !== input) {
                            hangulBuffer = [];
                        }
                        activeInput = input;
                        showKeyboard();
                    };

                    input.addEventListener('focus', handleFocus);
                    input.addEventListener('click', handleFocus);
                    input.addEventListener('input', () => {
                        activeInput = input;
                        if (input.value.trim() === "") {
                            showKeyboard();
                        }
                    });
                }
            });
        }"""

if old_js_bind in content:
    content = content.replace(old_js_bind, new_js_bind)
    print("Updated JavaScript checkAndBindInputs successfully.")
else:
    # Handle possible CRLF issues
    old_js_bind_crlf = old_js_bind.replace("\n", "\r\n")
    if old_js_bind_crlf in content:
        content = content.replace(old_js_bind_crlf, new_js_bind)
        print("Updated JavaScript checkAndBindInputs (CRLF) successfully.")
    else:
        print("Could not find old_js_bind!")

# 2. Insert st.fragments definitions at the top level (before sidebar starts)
old_sidebar_marker = "st.session_state.virtual_user_id = last_user\n\n\n# ────────────────────────────────────────────────────────────\n# Sidebar & User inputs"
old_sidebar_marker_crlf = "st.session_state.virtual_user_id = last_user\r\n\r\n\r\n# ────────────────────────────────────────────────────────────\r\n# Sidebar & User inputs"

# Define render_telegram_config_section, render_alert_section, render_virtual_trading_panel
fragments_definitions = '''st.session_state.virtual_user_id = last_user


# ────────────────────────────────────────────────────────────
# @st.fragment 컴포넌트 선언 (지정가 알림 / 가상 매매 / 텔레그램 연동 버퍼링 제거)
# ────────────────────────────────────────────────────────────
@st.fragment
def render_telegram_config_section():
    curr_token, curr_chat_id = alert_manager.get_token_and_chat_id()
    
    if "tg_success_msg" in st.session_state:
        st.success(st.session_state.pop("tg_success_msg"))
        
    tg_token = st.text_input(
        "텔레그램 봇 토큰",
        value=curr_token,
        type="password",
        placeholder="Bot Token 입력",
        key="tg_token_input"
    )
    tg_chat_id = st.text_input(
        "텔레그램 Chat ID",
        value=curr_chat_id,
        placeholder="Chat ID 입력",
        key="tg_chat_id_input"
    )
    
    def save_tg_config_callback():
        token = st.session_state.get("tg_token_input", "").strip()
        chat_id = st.session_state.get("tg_chat_id_input", "").strip()
        alert_manager.set_telegram_config(token, chat_id)
        st.session_state["tg_success_msg"] = "텔레그램 연동 설정이 저장되었습니다."
        
    st.button("연동 설정 저장", key="save_tg_config_btn", on_click=save_tg_config_callback)


@st.fragment
def render_alert_section(current_ticker):
    # 피보나치 레벨 알림 토글
    damus_tickers = alert_manager.get_damus_alert_tickers()
    is_damus_enabled = current_ticker in damus_tickers
    
    if "alert_success_msg" in st.session_state:
        st.success(st.session_state.pop("alert_success_msg"))
    if "alert_error_msg" in st.session_state:
        st.error(st.session_state.pop("alert_error_msg"))

    def damus_alert_callback():
        val = st.session_state.damus_alert_checkbox
        alert_manager.set_damus_alert_ticker(current_ticker, val)
        if not val:
            if getattr(alert_manager, '_damus_ticker', None) == current_ticker:
                alert_manager.stop_damus_monitor()
        st.session_state["alert_success_msg"] = f"{current_ticker} 피보나치 알림 설정이 변경되었습니다."

    st.checkbox(
        f"{current_ticker} 피보나치 레벨 알림 받기",
        value=is_damus_enabled,
        key="damus_alert_checkbox",
        on_change=damus_alert_callback
    )
        
    st.write("---")
    st.subheader("🔔 지정가 알림 등록")
    target_p = st.number_input(
        "목표 가격",
        min_value=0.0,
        value=None,
        placeholder="목표 가격을 입력하세요",
        step=0.01,
        key="alert_target_price_input"
    )
    cond = st.selectbox(
        "돌파 조건",
        options=["above", "below"],
        format_func=lambda x: "상향 돌파 (>=)" if x == "above" else "하향 돌파 (<=)",
        key="alert_condition_select"
    )

    def add_alert_callback():
        tp = st.session_state.get("alert_target_price_input")
        c = st.session_state.get("alert_condition_select", "above")
        if tp and tp > 0:
            alert_manager.add_alert(current_ticker, tp, c)
            if "alert_target_price_input" in st.session_state:
                del st.session_state["alert_target_price_input"]
            st.session_state["alert_success_msg"] = f"{current_ticker} 지정가 {tp} 알림이 추가되었습니다."
        else:
            st.session_state["alert_error_msg"] = "올바른 목표 가격을 입력해 주세요."

    st.button("지정가 알림 추가", key="add_price_alert_btn", on_click=add_alert_callback)
            
    st.write("---")
    st.subheader("📋 현재 등록된 알림 리스트")
    alerts = alert_manager.get_all_alerts()
    if not alerts:
        st.info("등록된 지정가 알림이 없습니다.")
    else:
        def delete_alert_callback(alert_id):
            alert_manager.remove_alert(alert_id)
            st.session_state["alert_success_msg"] = "지정가 알림이 삭제되었습니다."

        for a in alerts:
            ticker_lbl = a["ticker"]
            cond_lbl = "▲" if a["condition"] == "above" else "▼"
            price_lbl = f"{a['target_price']:,.2f}" if not (ticker_lbl.upper().endswith(".KS") or ticker_lbl.upper().endswith(".KQ")) else f"{a['target_price']:,.0f}"
            active_lbl = "" if a.get("is_active", True) else " (비활성)"
            
            col_a, col_b = st.columns([0.85, 0.15])
            col_a.markdown(f"**{ticker_lbl}** {cond_lbl} {price_lbl}{active_lbl}")
            col_b.button(
                "❌", 
                key=f"del_alert_{a['id']}", 
                help="알림 삭제",
                on_click=delete_alert_callback,
                args=(a['id'],)
            )


@st.fragment
def render_virtual_trading_panel(results):
    st.markdown("""
    <div style="background: rgba(30, 30, 40, 0.45); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 16px; padding: 20px; margin-bottom: 20px; box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);">
        <h3 style="color:#60A5FA; margin-top:0px; margin-bottom:5px; font-size: 20px;">💸 실시간 가상 매매 (Mock Trading)</h3>
        <p style="color:#94A3B8; font-size:12px; margin-bottom:0px;">포트폴리오 통합 조회 및 원클릭 매매 패널</p>
    </div>
    """, unsafe_allow_html=True)
    
    user_id_input = st.text_input(
        "👤 가상 매매 고유 닉네임 (영문/숫자/하이픈)", 
        value=st.session_state.virtual_user_id, 
        key="virtual_user_id_input_widget",
        help="나만의 고유한 닉네임을 설정하면 컴퓨터를 꺼두어도 주문이 유지되며, 재접속 시 이전 내역이 그대로 복구됩니다."
    )

    if user_id_input != st.session_state.virtual_user_id:
        st.session_state.virtual_user_id = user_id_input
        st.query_params["user"] = user_id_input
        try:
            with open(LAST_USER_FILE, "w", encoding="utf-8") as f:
                f.write(user_id_input)
        except Exception as e:
            print(f"[Last User Save Error] {e}")

    trading_user_id = st.session_state.virtual_user_id
    user_data = virtual_trading_manager.load_user_data(trading_user_id)

    usd_cash = user_data["usd_cash"]
    krw_cash = user_data["krw_cash"]
    portfolio = user_data["portfolio"]
    history = user_data["history"]
    limit_orders = user_data["limit_orders"]

    # 알림 메시지 처리
    if "trading_success_msg" in st.session_state:
        st.success(st.session_state.pop("trading_success_msg"))
    if "trading_error_msg" in st.session_state:
        st.error(st.session_state.pop("trading_error_msg"))
    if "trading_toast_msg" in st.session_state:
        st.toast(st.session_state.pop("trading_toast_msg"), icon="🔄")

    # 보유 현금량 정보 표시
    col_cash1, col_cash2 = st.columns(2)
    col_cash1.metric("💵 가상 USD 잔액", f"${usd_cash:,.2f}")
    col_cash2.metric("💵 가상 KRW 잔액", f"₩{krw_cash:,.0f}")

    # 📦 종합 보유 자산 현황
    st.markdown("#### 📦 종합 보유 자산 현황")
    if not portfolio:
        st.info("현재 보유 중인 가상 자산이 없습니다.")
    else:
        portfolio_rows = []
        for held_ticker, holding_item in portfolio.items():
            qty = holding_item["qty"]
            avg_p = holding_item["avg_price"]
            held_is_usd = holding_item.get("is_usd", True)
            
            cur_p = get_current_price_cached(held_ticker)
            if cur_p is None:
                cur_p = avg_p # fallback
                
            buy_amt = qty * avg_p
            val_amt = qty * cur_p
            pnl_amt = val_amt - buy_amt
            pct = (pnl_amt / buy_amt * 100) if buy_amt > 0 else 0.0
            
            symbol = "$" if held_is_usd else "₩"
            
            portfolio_rows.append({
                "자산": held_ticker,
                "보유 수량": f"{qty:,.4f}",
                "매수 평단": f"{symbol}{avg_p:,.2f}" if held_is_usd else f"{symbol}{avg_p:,.0f}",
                "현재가": f"{symbol}{cur_p:,.2f}" if held_is_usd else f"{symbol}{cur_p:,.0f}",
                "평가 금액": f"{symbol}{val_amt:,.2f}" if held_is_usd else f"{symbol}{val_amt:,.0f}",
                "평가 손익 (수익률)": f"{symbol}{pnl_amt:+,.2f} ({pct:+.2f}%)" if held_is_usd else f"{symbol}{pnl_amt:+,.0f} ({pct:+.2f}%)"
            })
        
        df_portfolio = pd.DataFrame(portfolio_rows)
        st.dataframe(df_portfolio, use_container_width=True, hide_index=True)

    # ⚡ 가상 거래 주문 설정
    st.markdown("#### ⚡ 가상 거래 주문 설정")
    
    asset_opts = [results['ticker']]
    for name, fav_t in st.session_state.favorites:
        if fav_t not in asset_opts:
            asset_opts.append(fav_t)
    for port_t in portfolio.keys():
        if port_t not in asset_opts:
            asset_opts.append(port_t)
            
    selected_order_ticker = st.selectbox(
        "주문 자산 선택",
        options=asset_opts,
        index=0,
        key="virtual_order_ticker_select_box",
        help="기본적으로 현재 분석 중인 자산이 선택되어 있으며, 보유 중이거나 즐겨찾기인 다른 자산도 선택할 수 있습니다."
    )
    
    if selected_order_ticker == results['ticker']:
        order_price = results['current_price']
        order_is_usd = results['is_usd']
    else:
        order_price = get_current_price_cached(selected_order_ticker)
        if order_price is None:
            order_price = portfolio.get(selected_order_ticker, {}).get("avg_price", 0.0)
        order_is_usd = not (selected_order_ticker.upper().endswith('.KS') or selected_order_ticker.upper().endswith('.KQ'))
        
    currency_symbol = "$" if order_is_usd else "₩"
    
    if order_price == 0.0:
        st.warning("⚠️ 선택한 자산의 실시간 시세를 가져올 수 없어 주문을 진행할 수 없습니다.")
    else:
        st.markdown(f"**{selected_order_ticker}** 현재 시세: **{currency_symbol}{order_price:,.2f}**" if order_is_usd else f"**{selected_order_ticker}** 현재 시세: **{currency_symbol}{order_price:,.0f}**")
        
        order_type = st.radio(
            "주문 유형", 
            ["시장가 (즉시 체결)", "지정가 (예약 체결)"], 
            horizontal=True, 
            key="virtual_order_type_select_sidebar"
        )
        
        selected_holding = portfolio.get(selected_order_ticker, {"qty": 0.0, "avg_price": 0.0, "is_usd": order_is_usd})
        held_qty = selected_holding["qty"]
        
        col_tr_buy, col_tr_sell = st.columns(2)
        
        with col_tr_buy:
            st.markdown("**🟢 매수 주문 (BUY)**")
            max_buy_cash = usd_cash if order_is_usd else krw_cash
            
            if order_type == "지정가 (예약 체결)":
                limit_buy_price = st.number_input(
                    "매수 지정가 입력",
                    min_value=0.0,
                    value=None,
                    placeholder=f"현재가: {order_price:,.2f}",
                    step=order_price/100 if order_price > 0 else 1.0,
                    key="limit_buy_price_input_col"
                )
                buy_amount = st.number_input(
                    "매수 금액 입력",
                    min_value=0.0,
                    max_value=float(max_buy_cash),
                    value=None,
                    placeholder="금액을 입력하세요",
                    step=100.0 if order_is_usd else 100000.0,
                    key="buy_amount_input_limit_col"
                )
                _lbp = limit_buy_price or 0.0
                _ba  = buy_amount or 0.0
                exp_qty = _ba / _lbp if _lbp > 0 else 0.0
                st.caption(f"예상 매수: **{exp_qty:,.4f} {selected_order_ticker.split('-')[0]}**")

                def execute_limit_buy_callback():
                    lbp = st.session_state.get("limit_buy_price_input_col") or 0.0
                    ba = st.session_state.get("buy_amount_input_limit_col") or 0.0
                    if ba <= 0:
                        st.session_state["trading_error_msg"] = "매수 금액을 입력해 주세요."
                    elif lbp <= 0:
                        st.session_state["trading_error_msg"] = "올바른 지정가 가격을 입력해 주세요."
                    elif ba > max_buy_cash:
                        st.session_state["trading_error_msg"] = "잔액이 부족합니다."
                    else:
                        success, msg = virtual_trading_manager.add_limit_buy(trading_user_id, selected_order_ticker, lbp, ba, order_is_usd)
                        if success:
                            for _k in ["limit_buy_price_input_col", "buy_amount_input_limit_col"]:
                                if _k in st.session_state:
                                    del st.session_state[_k]
                            st.session_state["trading_success_msg"] = msg
                        else:
                            st.session_state["trading_error_msg"] = msg
                
                st.button("🔴 지정가 매수 예약", key="execute_limit_buy_btn_col", use_container_width=True, on_click=execute_limit_buy_callback)
            else:
                buy_amount = st.number_input(
                    "매수 금액 입력",
                    min_value=0.0,
                    max_value=float(max_buy_cash),
                    value=None,
                    placeholder="금액을 입력하세요",
                    step=100.0 if order_is_usd else 100000.0,
                    key="buy_amount_input_market_col"
                )
                _ba2 = buy_amount or 0.0
                exp_qty = _ba2 / order_price if order_price > 0 else 0.0
                st.caption(f"예상 매수: **{exp_qty:,.4f} {selected_order_ticker.split('-')[0]}**")

                def execute_market_buy_callback():
                    ba2 = st.session_state.get("buy_amount_input_market_col") or 0.0
                    if ba2 <= 0:
                        st.session_state["trading_error_msg"] = "매수 금액을 입력해 주세요."
                    elif ba2 > max_buy_cash:
                        st.session_state["trading_error_msg"] = "잔액이 부족합니다."
                    else:
                        success, msg = virtual_trading_manager.execute_market_buy(trading_user_id, selected_order_ticker, ba2, order_price, order_is_usd)
                        if success:
                            if "buy_amount_input_market_col" in st.session_state:
                                del st.session_state["buy_amount_input_market_col"]
                            st.session_state["trading_success_msg"] = msg
                        else:
                            st.session_state["trading_error_msg"] = msg

                st.button("🔴 시장가 매수 실행", key="execute_market_buy_btn_col", use_container_width=True, on_click=execute_market_buy_callback)
                            
        with col_tr_sell:
            st.markdown("**🔴 매도 주문 (SELL)**")
            
            if order_type == "지정가 (예약 체결)":
                limit_sell_price = st.number_input(
                    "매도 지정가 입력",
                    min_value=0.0,
                    value=None,
                    placeholder=f"현재가: {order_price:,.2f}",
                    step=order_price/100 if order_price > 0 else 1.0,
                    key="limit_sell_price_input_col"
                )
                sell_qty = st.number_input(
                    "매도 수량 입력",
                    min_value=0.0,
                    max_value=float(held_qty),
                    value=None,
                    placeholder="수량을 입력하세요",
                    step=held_qty/10 if held_qty > 0 else 0.1,
                    key="sell_qty_input_limit_col"
                )
                _lsp = limit_sell_price or 0.0
                _sq  = sell_qty or 0.0
                exp_recv = _sq * _lsp
                st.caption(f"예상 정산: **{currency_symbol}{exp_recv:,.2f}**" if order_is_usd else f"예상 정산: **{currency_symbol}{exp_recv:,.0f}**")
                
                def execute_limit_sell_callback():
                    lsp = st.session_state.get("limit_sell_price_input_col") or 0.0
                    sq = st.session_state.get("sell_qty_input_limit_col") or 0.0
                    if sq <= 0:
                        st.session_state["trading_error_msg"] = "매도 수량을 입력해 주세요."
                    elif lsp <= 0:
                        st.session_state["trading_error_msg"] = "올바른 지정가 가격을 입력해 주세요."
                    elif sq > held_qty:
                        st.session_state["trading_error_msg"] = "보유 수량이 부족합니다."
                    else:
                        success, msg = virtual_trading_manager.add_limit_sell(trading_user_id, selected_order_ticker, lsp, sq, order_is_usd)
                        if success:
                            for _k in ["limit_sell_price_input_col", "sell_qty_input_limit_col"]:
                                if _k in st.session_state:
                                    del st.session_state[_k]
                            st.session_state["trading_success_msg"] = msg
                        else:
                            st.session_state["trading_error_msg"] = msg

                st.button("🟢 지정가 매도 예약", key="execute_limit_sell_btn_col", use_container_width=True, on_click=execute_limit_sell_callback)
            else:
                sell_qty = st.number_input(
                    "매도 수량 입력",
                    min_value=0.0,
                    max_value=float(held_qty),
                    value=None,
                    placeholder="수량을 입력하세요",
                    step=held_qty/10 if held_qty > 0 else 0.1,
                    key="sell_qty_input_market_col"
                )
                _sq2 = sell_qty or 0.0
                exp_recv = _sq2 * order_price
                st.caption(f"예상 정산: **{currency_symbol}{exp_recv:,.2f}**" if order_is_usd else f"예상 정산: **{currency_symbol}{exp_recv:,.0f}**")
                
                def execute_market_sell_callback():
                    sq2 = st.session_state.get("sell_qty_input_market_col") or 0.0
                    if sq2 <= 0:
                        st.session_state["trading_error_msg"] = "매도 수량을 입력해 주세요."
                    elif sq2 > held_qty:
                        st.session_state["trading_error_msg"] = "보유 수량이 부족합니다."
                    else:
                        success, msg = virtual_trading_manager.execute_market_sell(trading_user_id, selected_order_ticker, sq2, order_price, order_is_usd)
                        if success:
                            if "sell_qty_input_market_col" in st.session_state:
                                del st.session_state["sell_qty_input_market_col"]
                            st.session_state["trading_success_msg"] = msg
                        else:
                            st.session_state["trading_error_msg"] = msg

                st.button("🟢 시장가 매도 실행", key="execute_market_sell_btn_col", use_container_width=True, on_click=execute_market_sell_callback)

        # ⏳ 통합 대기 중인 지정가 주문 목록 (전체 자산)
        st.markdown("#### ⏳ 대기 중인 지정가 주문 목록")
        if not limit_orders:
            st.caption("대기 중인 지정가 주문이 없습니다.")
        else:
            def cancel_order_callback(order_id):
                success, msg = virtual_trading_manager.cancel_limit_order(trading_user_id, order_id)
                if success:
                    st.session_state["trading_toast_msg"] = msg
                else:
                    st.session_state["trading_error_msg"] = msg

            for idx, order in enumerate(limit_orders):
                o_curr = "$" if order["is_usd"] else "₩"
                col_o1, col_o2 = st.columns([0.75, 0.25])
                with col_o1:
                    st.markdown(f"📌 **{order['ticker']}** | {order['type'].split('(')[0].strip()}\n* 목표가: {o_curr}{order['target_price']:,.2f} | 수량: {order['qty']:,.4f}")
                with col_o2:
                    st.button(
                        "취소 ❌", 
                        key=f"cancel_order_col_{order['id']}_{idx}", 
                        use_container_width=True,
                        on_click=cancel_order_callback,
                        args=(order["id"],)
                    )
                            
        # 매매 이력 로그 및 리셋
        with st.expander("📜 가상 거래 내역 및 계좌 관리"):
            if history:
                history_df = pd.DataFrame(history[::-1])
                st.dataframe(history_df, use_container_width=True, hide_index=True)
            else:
                st.caption("거래 내역이 없습니다.")
            
            st.write("---")

            def reset_account_callback():
                virtual_trading_manager.reset_user_data(trading_user_id)
                st.session_state["trading_toast_msg"] = "가상 계좌가 초기 상태로 재설정되었습니다!"

            st.button(
                "🔄 가상 계좌 초기화 (자산 리셋)", 
                key="reset_virtual_trading_btn_col", 
                use_container_width=True,
                on_click=reset_account_callback
            )


# ────────────────────────────────────────────────────────────
# Sidebar & User inputs'''

if old_sidebar_marker in content:
    content = content.replace(old_sidebar_marker, fragments_definitions)
    print("Inserted fragments definitions successfully.")
elif old_sidebar_marker_crlf in content:
    content = content.replace(old_sidebar_marker_crlf, fragments_definitions)
    print("Inserted fragments definitions (CRLF) successfully.")
else:
    print("Could not find old_sidebar_marker!")

# 3. Replace the Telegram Configuration inside sidebar with render_telegram_config_section()
old_telegram_block = """    # ────────────────────────────────────────────────────────────
    # 🚨 텔레그램 알림 설정
    # ────────────────────────────────────────────────────────────
    st.write("---")
    with st.expander("🚨 텔레그램 알림 설정"):
        st.subheader("🔑 텔레그램 연동 설정")
        curr_token, curr_chat_id = alert_manager.get_token_and_chat_id()
        
        tg_token = st.text_input(
            "텔레그램 봇 토큰",
            value=curr_token,
            type="password",
            placeholder="Bot Token 입력",
            key="tg_token_input"
        )
        tg_chat_id = st.text_input(
            "텔레그램 Chat ID",
            value=curr_chat_id,
            placeholder="Chat ID 입력",
            key="tg_chat_id_input"
        )
        if st.button("연동 설정 저장", key="save_tg_config_btn"):
            alert_manager.set_telegram_config(tg_token.strip(), tg_chat_id.strip())
            st.success("텔레그램 연동 설정이 저장되었습니다.")
            st.rerun()
            
        st.write("---")
        render_alert_section(current_ticker)"""

new_telegram_block = """    # ────────────────────────────────────────────────────────────
    # 🚨 텔레그램 알림 설정
    # ────────────────────────────────────────────────────────────
    st.write("---")
    with st.expander("🚨 텔레그램 알림 설정"):
        st.subheader("🔑 텔레그램 연동 설정")
        render_telegram_config_section()
            
        st.write("---")
        render_alert_section(current_ticker)"""

if old_telegram_block in content:
    content = content.replace(old_telegram_block, new_telegram_block)
    print("Replaced Telegram settings block successfully.")
else:
    old_telegram_block_crlf = old_telegram_block.replace("\n", "\r\n")
    if old_telegram_block_crlf in content:
        content = content.replace(old_telegram_block_crlf, new_telegram_block)
        print("Replaced Telegram settings block (CRLF) successfully.")
    else:
        print("Could not find old_telegram_block!")

# 4. Replace Virtual Trading Panel in right column with render_virtual_trading_panel(results)
# Since we reverted, the old virtual trading block is back.
# We match 'with right_col:' up to the dashboard try-except block
old_right_col = """        if show_virtual_trading:
            with right_col:
                # 💸 실시간 가상 매매 (Mock Trading) 패널 상시 노출
                st.markdown(\"\"\"
                <div style="background: rgba(30, 30, 40, 0.45); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 16px; padding: 20px; margin-bottom: 20px; box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);">
                    <h3 style="color:#60A5FA; margin-top:0px; margin-bottom:5px; font-size: 20px;">💸 실시간 가상 매매 (Mock Trading)</h3>
                    <p style="color:#94A3B8; font-size:12px; margin-bottom:0px;">포트폴리오 통합 조회 및 원클릭 매매 패널</p>
                </div>
                \"\"\", unsafe_allow_html=True)
                
                # 사용자 닉네임 입력 추가
                user_id_input = st.text_input(
                    "👤 가상 매매 고유 닉네임 (영문/숫자/하이픈)", 
                    value=st.session_state.virtual_user_id, 
                    key="virtual_user_id_input_widget",
                    help="나만의 고유한 닉네임을 설정하면 컴퓨터를 꺼두어도 주문이 유지되며, 재접속 시 이전 내역이 그대로 복구됩니다."
                )
    
                # 입력한 닉네임 세션 및 URL 파라미터 동기화
                if user_id_input != st.session_state.virtual_user_id:
                    st.session_state.virtual_user_id = user_id_input
                    st.query_params["user"] = user_id_input
                    # 로컬 파일에 마지막 닉네임 저장
                    try:
                        with open(LAST_USER_FILE, "w", encoding="utf-8") as f:
                            f.write(user_id_input)
                    except Exception as e:
                        print(f"[Last User Save Error] {e}")
                    st.rerun()
    
                trading_user_id = st.session_state.virtual_user_id
                user_data = virtual_trading_manager.load_user_data(trading_user_id)
    
                usd_cash = user_data["usd_cash"]
                krw_cash = user_data["krw_cash"]
                portfolio = user_data["portfolio"]
                history = user_data["history"]
                limit_orders = user_data["limit_orders"]
    
                # 보유 현금량 정보 표시
                col_cash1, col_cash2 = st.columns(2)
                col_cash1.metric("💵 가상 USD 잔액", f"${usd_cash:,.2f}")
                col_cash2.metric("💵 가상 KRW 잔액", f"₩{krw_cash:,.0f}")
    
                # 📦 종합 보유 자산 현황
                st.markdown("#### 📦 종합 보유 자산 현황")
                if not portfolio:
                    st.info("현재 보유 중인 가상 자산이 없습니다.")
                else:
                    portfolio_rows = []
                    for held_ticker, holding_item in portfolio.items():
                        qty = holding_item["qty"]
                        avg_p = holding_item["avg_price"]
                        held_is_usd = holding_item.get("is_usd", True)
                        
                        cur_p = get_current_price_cached(held_ticker)
                        if cur_p is None:
                            cur_p = avg_p # fallback
                            
                        buy_amt = qty * avg_p
                        val_amt = qty * cur_p
                        pnl_amt = val_amt - buy_amt
                        pct = (pnl_amt / buy_amt * 100) if buy_amt > 0 else 0.0
                        
                        symbol = "$" if held_is_usd else "₩"
                        
                        portfolio_rows.append({
                            "자산": held_ticker,
                            "보유 수량": f"{qty:,.4f}",
                            "매수 평단": f"{symbol}{avg_p:,.2f}" if held_is_usd else f"{symbol}{avg_p:,.0f}",
                            "현재가": f"{symbol}{cur_p:,.2f}" if held_is_usd else f"{symbol}{cur_p:,.0f}",
                            "평가 금액": f"{symbol}{val_amt:,.2f}" if held_is_usd else f"{symbol}{val_amt:,.0f}",
                            "평가 손익 (수익률)": f"{symbol}{pnl_amt:+,.2f} ({pct:+.2f}%)" if held_is_usd else f"{symbol}{pnl_amt:+,.0f} ({pct:+.2f}%)"
                        })
                    
                    df_portfolio = pd.DataFrame(portfolio_rows)
                    st.dataframe(df_portfolio, use_container_width=True, hide_index=True)
    
                # ⚡ 가상 거래 주문 설정
                st.markdown("#### ⚡ 가상 거래 주문 설정")
                
                # 주문 대상 자산 선택 리스트 구성
                asset_opts = [results['ticker']]
                for name, fav_t in st.session_state.favorites:
                    if fav_t not in asset_opts:
                        asset_opts.append(fav_t)
                for port_t in portfolio.keys():
                    if port_t not in asset_opts:
                        asset_opts.append(port_t)
                        
                selected_order_ticker = st.selectbox(
                    "주문 자산 선택",
                    options=asset_opts,
                    index=0,
                    key="virtual_order_ticker_select_box",
                    help="기본적으로 현재 분석 중인 자산이 선택되어 있으며, 보유 중이거나 즐겨찾기인 다른 자산도 선택할 수 있습니다."
                )
                
                # 선택된 자산에 대한 현재가 및 화폐 단위 판단
                if selected_order_ticker == results['ticker']:
                    order_price = results['current_price']
                    order_is_usd = results['is_usd']
                else:
                    order_price = get_current_price_cached(selected_order_ticker)
                    if order_price is None:
                        # 포트폴리오에 평단가가 있으면 그것으로 대체
                        order_price = portfolio.get(selected_order_ticker, {}).get("avg_price", 0.0)
                    order_is_usd = not (selected_order_ticker.upper().endswith('.KS') or selected_order_ticker.upper().endswith('.KQ'))
                    
                currency_symbol = "$" if order_is_usd else "₩"
                
                if order_price == 0.0:
                    st.warning("⚠️ 선택한 자산의 실시간 시세를 가져올 수 없어 주문을 진행할 수 없습니다.")
                else:
                    st.markdown(f"**{selected_order_ticker}** 현재 시세: **{currency_symbol}{order_price:,.2f}**" if order_is_usd else f"**{selected_order_ticker}** 현재 시세: **{currency_symbol}{order_price:,.0f}**")
                    
                    order_type = st.radio(
                        "주문 유형", 
                        ["시장가 (즉시 체결)", "지정가 (예약 체결)"], 
                        horizontal=True, 
                        key="virtual_order_type_select_sidebar"
                    )
                    
                    # 주문 대상 자산에 대한 보유 수량 정보
                    selected_holding = portfolio.get(selected_order_ticker, {"qty": 0.0, "avg_price": 0.0, "is_usd": order_is_usd})
                    held_qty = selected_holding["qty"]
                    
                    col_tr_buy, col_tr_sell = st.columns(2)
                    
                    with col_tr_buy:
                        st.markdown("**🟢 매수 주문 (BUY)**")
                        max_buy_cash = usd_cash if order_is_usd else krw_cash
                        
                        if order_type == "지정가 (예약 체결)":
                            limit_buy_price = st.number_input(
                                "매수 지정가 입력",
                                min_value=0.0,
                                value=None,
                                placeholder=f"현재가: {order_price:,.2f}",
                                step=order_price/100 if order_price > 0 else 1.0,
                                key="limit_buy_price_input_col"
                            )
                            buy_amount = st.number_input(
                                "매수 금액 입력",
                                min_value=0.0,
                                max_value=float(max_buy_cash),
                                value=None,
                                placeholder="금액을 입력하세요",
                                step=100.0 if order_is_usd else 100000.0,
                                key="buy_amount_input_limit_col"
                            )
                            _lbp = limit_buy_price or 0.0
                            _ba  = buy_amount or 0.0
                            exp_qty = _ba / _lbp if _lbp > 0 else 0.0
                            st.caption(f"예상 매수: **{exp_qty:,.4f} {selected_order_ticker.split('-')[0]}**")
                            
                            if st.button("🔴 지정가 매수 예약", key="execute_limit_buy_btn_col", use_container_width=True):
                                _lbp = limit_buy_price or 0.0
                                _ba  = buy_amount or 0.0
                                if _ba <= 0:
                                    st.error("매수 금액을 입력해 주세요.")
                                elif _lbp <= 0:
                                    st.error("올바른 지정가 가격을 입력해 주세요.")
                                elif _ba > max_buy_cash:
                                    st.error("잔액이 부족합니다.")
                                else:
                                    success, msg = virtual_trading_manager.add_limit_buy(trading_user_id, selected_order_ticker, _lbp, _ba, order_is_usd)
                                    if success:
                                        for _k in ["limit_buy_price_input_col", "buy_amount_input_limit_col"]:
                                            if _k in st.session_state:
                                                del st.session_state[_k]
                                        st.success(msg)
                                        st.rerun()
                                    else:
                                        st.error(msg)
                        else:
                            buy_amount = st.number_input(
                                "매수 금액 입력",
                                min_value=0.0,
                                max_value=float(max_buy_cash),
                                value=None,
                                placeholder="금액을 입력하세요",
                                step=100.0 if order_is_usd else 100000.0,
                                key="buy_amount_input_market_col"
                            )
                            _ba2 = buy_amount or 0.0
                            exp_qty = _ba2 / order_price if order_price > 0 else 0.0
                            st.caption(f"예상 매수: **{exp_qty:,.4f} {selected_order_ticker.split('-')[0]}**")
 
                            if st.button("🔴 시장가 매수 실행", key="execute_market_buy_btn_col", use_container_width=True):
                                if _ba2 <= 0:
                                    st.error("매수 금액을 입력해 주세요.")
                                elif _ba2 > max_buy_cash:
                                    st.error("잔액이 부족합니다.")
                                else:
                                    success, msg = virtual_trading_manager.execute_market_buy(trading_user_id, selected_order_ticker, _ba2, order_price, order_is_usd)
                                    if success:
                                        if "buy_amount_input_market_col" in st.session_state:
                                            del st.session_state["buy_amount_input_market_col"]
                                        st.success(msg)
                                        st.rerun()
                                    else:
                                        st.error(msg)
                                        
                    with col_tr_sell:
                        st.markdown("**🔴 매도 주문 (SELL)**")
                        
                        if order_type == "지정가 (예약 체결)":
                            limit_sell_price = st.number_input(
                                "매도 지정가 입력",
                                min_value=0.0,
                                value=None,
                                placeholder=f"현재가: {order_price:,.2f}",
                                step=order_price/100 if order_price > 0 else 1.0,
                                key="limit_sell_price_input_col"
                            )
                            sell_qty = st.number_input(
                                "매도 수량 입력",
                                min_value=0.0,
                                max_value=float(held_qty),
                                value=None,
                                placeholder="수량을 입력하세요",
                                step=held_qty/10 if held_qty > 0 else 0.1,
                                key="sell_qty_input_limit_col"
                            )
                            _lsp = limit_sell_price or 0.0
                            _sq  = sell_qty or 0.0
                            exp_recv = _sq * _lsp
                            st.caption(f"예상 정산: **{currency_symbol}{exp_recv:,.2f}**" if order_is_usd else f"예상 정산: **{currency_symbol}{exp_recv:,.0f}**")
                            
                            if st.button("🟢 지정가 매도 예약", key="execute_limit_sell_btn_col", use_container_width=True):
                                _lsp = limit_sell_price or 0.0
                                _sq  = sell_qty or 0.0
                                if _sq <= 0:
                                    st.error("매도 수량을 입력해 주세요.")
                                elif _lsp <= 0:
                                    st.error("올바른 지정가 가격을 입력해 주세요.")
                                elif _sq > held_qty:
                                    st.error("보유 수량이 부족합니다.")
                                else:
                                    success, msg = virtual_trading_manager.add_limit_sell(trading_user_id, selected_order_ticker, _lsp, _sq, order_is_usd)
                                    if success:
                                        for _k in ["limit_sell_price_input_col", "sell_qty_input_limit_col"]:
                                            if _k in st.session_state:
                                                del st.session_state[_k]
                                        st.success(msg)
                                        st.rerun()
                                    else:
                                        st.error(msg)
                        else:
                            sell_qty = st.number_input(
                                "매도 수량 입력",
                                min_value=0.0,
                                max_value=float(held_qty),
                                value=None,
                                placeholder="수량을 입력하세요",
                                step=held_qty/10 if held_qty > 0 else 0.1,
                                key="sell_qty_input_market_col"
                            )
                            _sq2 = sell_qty or 0.0
                            exp_recv = _sq2 * order_price
                            st.caption(f"예상 정산: **{currency_symbol}{exp_recv:,.2f}**" if order_is_usd else f"예상 정산: **{currency_symbol}{exp_recv:,.0f}**")
                            
                            if st.button("🟢 시장가 매도 실행", key="execute_market_sell_btn_col", use_container_width=True):
                                if _sq2 <= 0:
                                    st.error("매도 수량을 입력해 주세요.")
                                elif _sq2 > held_qty:
                                    st.error("보유 수량이 부족합니다.")
                                else:
                                    success, msg = virtual_trading_manager.execute_market_sell(trading_user_id, selected_order_ticker, _sq2, order_price, order_is_usd)
                                    if success:
                                        if "sell_qty_input_market_col" in st.session_state:
                                            del st.session_state["sell_qty_input_market_col"]
                                        st.success(msg)
                                        st.rerun()
                                    else:
                                        st.error(msg)
     
                # ⏳ 통합 대기 중인 지정가 주문 목록 (전체 자산)
                st.markdown("#### ⏳ 대기 중인 지정가 주문 목록")
                if not limit_orders:
                    st.caption("대기 중인 지정가 주문이 없습니다.")
                else:
                    for idx, order in enumerate(limit_orders):
                        o_curr = "$" if order["is_usd"] else "₩"
                        col_o1, col_o2 = st.columns([0.75, 0.25])
                        with col_o1:
                            st.markdown(f"📌 **{order['ticker']}** | {order['type'].split('(')[0].strip()}\n* 목표가: {o_curr}{order['target_price']:,.2f} | 수량: {order['qty']:,.4f}")
                        with col_o2:
                            if st.button("취소 ❌", key=f"cancel_order_col_{order['id']}_{idx}", use_container_width=True):
                                success, msg = virtual_trading_manager.cancel_limit_order(trading_user_id, order["id"])
                                if success:
                                    st.toast(msg, icon="❌")
                                    st.rerun()
                                else:
                                    st.error(msg)
                                    
                # 매매 이력 로그 및 리셋
                with st.expander("📜 가상 거래 내역 및 계좌 관리"):
                    if history:
                        history_df = pd.DataFrame(history[::-1])
                        st.dataframe(history_df, use_container_width=True, hide_index=True)
                    else:
                        st.caption("거래 내역이 없습니다.")
                    
                    st.write("---")
                    if st.button("🔄 가상 계좌 초기화 (자산 리셋)", key="reset_virtual_trading_btn_col", use_container_width=True):
                        virtual_trading_manager.reset_user_data(trading_user_id)
                        st.toast("가상 계좌가 초기 상태로 재설정되었습니다!", icon="🔄")
                        st.rerun())"""

new_right_col = """        if show_virtual_trading:
            with right_col:
                render_virtual_trading_panel(results)"""

if old_right_col in content:
    content = content.replace(old_right_col, new_right_col)
    print("Replaced right_col block successfully.")
else:
    # Handle possible CRLF issues
    old_right_col_crlf = old_right_col.replace("\n", "\r\n")
    # Clean it slightly in case of minor quote formatting
    content_normalized = content.replace("\r\n", "\n")
    old_right_col_normalized = old_right_col.replace("\r\n", "\n")
    if old_right_col_normalized in content_normalized:
        content_normalized = content_normalized.replace(old_right_col_normalized, new_right_col)
        content = content_normalized
        print("Replaced right_col block (normalized) successfully.")
    else:
        print("Could not find old_right_col!")

# 5. Write the modified content back
with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Finished all optimizations in optimize_v2.py!")
