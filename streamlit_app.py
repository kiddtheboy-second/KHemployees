import streamlit as st
from snowflake.snowpark.context import get_active_session
import json
import re
import pandas as pd

session = get_active_session()

st.title("금호건설 임직원 검색 봇")
st.caption("이름, 담당업무, 팀, 연락처 등으로 검색하세요.")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_dept" not in st.session_state:
    st.session_state.last_dept = None

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if isinstance(msg["content"], pd.DataFrame):
            st.dataframe(msg["content"], use_container_width=True)
        else:
            st.write(msg["content"])

MAX_LIST_COUNT = 50

# ============================================================
# 부서 관련 함수
# ============================================================

def get_all_depts():
    """dept + parent_dept 모두 수집해서 검색 커버리지 확대"""
    if "all_depts" not in st.session_state:
        rows = session.sql("""
            SELECT DISTINCT dept, parent_dept
            FROM CONSTRUCTION_RAG.DOCS.employees
            WHERE dept IS NOT NULL
        """).collect()
        # dept와 parent_dept 모두 등록 (중복 제거)
        depts = set()
        for r in rows:
            if r["DEPT"]:
                depts.add(r["DEPT"])
            if r["PARENT_DEPT"]:
                depts.add(r["PARENT_DEPT"])
        # 긴 부서명이 먼저 매칭되도록 정렬 (DI팀(고속파트) > DI팀)
        st.session_state.all_depts = sorted(depts, key=len, reverse=True)
    return st.session_state.all_depts

def extract_dept(query):
    depts = get_all_depts()
    for dept in depts:
        if dept in query:
            return dept
    return None

def resolve_dept(query):
    """현재 쿼리에서 부서 감지, 없으면 직전 부서 자동 사용"""
    detected = extract_dept(query)
    if detected:
        st.session_state.last_dept = detected
        return detected
    if st.session_state.last_dept and (is_list_all_search(query) or is_count_search(query)):
        return st.session_state.last_dept
    return None

def build_dept_where(dept):
    """
    부서 필터 WHERE 조건 생성
    - 정확한 부서명 → dept = 'DI팀(고속파트)'
    - 상위 부서명 → parent_dept = 'DI팀' (하위조직 포함)
    """
    if not dept:
        return ""
    # 해당 dept가 parent_dept로 존재하는지 확인 (하위조직 있는 경우)
    rows = session.sql(f"""
        SELECT COUNT(*) AS cnt
        FROM CONSTRUCTION_RAG.DOCS.employees
        WHERE parent_dept = '{dept}' AND dept != '{dept}'
    """).collect()
    has_sub = rows[0]["CNT"] > 0

    if has_sub:
        # 상위부서로 검색 시 하위조직 포함 여부를 사용자에게 묻지 않고
        # parent_dept 기준으로 전체 포함
        return f"parent_dept = '{dept}'"
    else:
        return f"dept = '{dept}'"

# ============================================================
# 검색 유형 판단 함수
# ============================================================

def is_number_search(query):
    return bool(re.search(r'\d{4,}', query))

def is_count_search(query):
    keywords = ["몇명", "몇 명", "몇분", "몇 분", "총원", "몇명이야", "몇명인지", "인원수", "몇명있"]
    return any(k in query for k in keywords)

def is_list_all_search(query):
    keywords = ["전체", "모두", "리스트", "목록", "다 알려", "전원", "인원"]
    return any(k in query for k in keywords)

# ============================================================
# SQL 실행 함수
# ============================================================

def get_count(dept=None):
    where = "WHERE name != '그룹웨어관리'"
    if dept:
        dept_cond = build_dept_where(dept)
        if dept_cond:
            where += f" AND {dept_cond}"
    return session.sql(f"""
        SELECT COUNT(*) AS cnt
        FROM CONSTRUCTION_RAG.DOCS.employees
        {where}
    """).collect()[0]["CNT"]

def sql_list(dept=None):
    where = "WHERE name != '그룹웨어관리'"
    if dept:
        dept_cond = build_dept_where(dept)
        if dept_cond:
            where += f" AND {dept_cond}"
    return session.sql(f"""
        SELECT name, position, role, task, email, mobile,
               office_tel, extension_no, dept, is_duplicate_name
        FROM CONSTRUCTION_RAG.DOCS.employees
        {where}
        ORDER BY dept, position, name
    """).collect()

def sql_number_search(query):
    """전화번호 + 내선번호 동시 검색"""
    numbers = re.findall(r'\d+', query)
    conditions = " OR ".join([
        f"mobile LIKE '%{n}%' OR office_tel LIKE '%{n}%' OR extension_no LIKE '%{n}%'"
        for n in numbers
    ])
    return session.sql(f"""
        SELECT name, position, role, task, email, mobile,
               office_tel, extension_no, dept, is_duplicate_name
        FROM CONSTRUCTION_RAG.DOCS.employees
        WHERE {conditions}
    """).collect()

def cortex_search(query):
    result = session.sql(f"""
        SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
            'CONSTRUCTION_RAG.DOCS.employees_search',
            '{{"query": "{query}", "columns": ["name","task","position","email","mobile","office_tel","extension_no","dept"], "limit": 5}}'
        ) AS result
    """).collect()[0]["RESULT"]
    return json.loads(result).get("results", [])

# ============================================================
# 데이터 변환 함수
# ============================================================

def rows_to_dataframe(rows, is_dict=False):
    if is_dict:
        data = [{
            "이름": r.get("name", ""),
            "부서": r.get("dept", ""),
            "직위": r.get("position", ""),
            "직책": r.get("role", ""),
            "담당업무": r.get("task", ""),
            "메일": r.get("email", ""),
            "핸드폰": r.get("mobile", ""),
            "회사번호": r.get("office_tel", ""),
            "내선번호": r.get("extension_no", ""),      # ✅ 추가
        } for r in rows]
    else:
        data = [{
            "이름": r["NAME"],
            "부서": r["DEPT"],
            "직위": r["POSITION"],
            "직책": r["ROLE"],
            "담당업무": r["TASK"],
            "메일": r["EMAIL"],
            "핸드폰": r["MOBILE"],
            "회사번호": r["OFFICE_TEL"],
            "내선번호": r["EXTENSION_NO"],              # ✅ 추가
        } for r in rows]
    df = pd.DataFrame(data)
    df.index = df.index + 1
    return df

def rows_to_context(rows, is_dict=False):
    lines = []
    for r in rows:
        if is_dict:
            lines.append(
                f"이름: {r.get('name','')} / 부서: {r.get('dept','')} / "
                f"직위: {r.get('position','')} / 담당업무: {r.get('task','')} / "
                f"메일: {r.get('email','')} / 핸드폰: {r.get('mobile','')} / "
                f"회사번호: {r.get('office_tel','')} / 내선번호: {r.get('extension_no','')}"  # ✅ 추가
            )
        else:
            lines.append(
                f"이름: {r['NAME']} / 부서: {r['DEPT']} / "
                f"직위: {r['POSITION']} / 담당업무: {r['TASK']} / "
                f"메일: {r['EMAIL']} / 핸드폰: {r['MOBILE']} / "
                f"회사번호: {r['OFFICE_TEL']} / 내선번호: {r['EXTENSION_NO']}"  # ✅ 추가
            )
    return "\n".join(lines)

def check_duplicate_name(rows, is_dict=False):
    """동명이인 존재 여부 확인"""
    if is_dict:
        return any(r.get("is_duplicate_name", False) for r in rows)
    else:
        return any(r["IS_DUPLICATE_NAME"] for r in rows)

# ============================================================
# LLM 호출
# ============================================================

def build_history():
    history = []
    recent = [m for m in st.session_state.messages
              if not isinstance(m["content"], pd.DataFrame)][-6:]
    for msg in recent:
        role = "user" if msg["role"] == "user" else "assistant"
        history.append({"role": role, "content": str(msg["content"])})
    return history

def ask_llm(context, query, has_duplicate=False):
    history = build_history()
    history_text = "\n".join([
        f"{'사용자' if h['role'] == 'user' else '봇'}: {h['content']}"
        for h in history
    ])
    # ✅ 동명이인 안내 규칙 추가
    duplicate_rule = (
        "6. 동명이인이 존재합니다. 이름만으로는 특정이 어려우니 부서나 담당업무도 함께 안내하세요."
        if has_duplicate else ""
    )
    prompt = f"""당신은 금호건설 임직원 정보 안내 봇입니다.
규칙:
1. 반드시 아래 제공된 데이터에 있는 값만 그대로 사용하세요.
2. 직위 등 어떤 정보도 절대 추론하거나 변환하지 마세요.
3. 데이터에 없는 내용은 절대 답하지 마세요.
4. 부서명은 항상 함께 안내하세요.
5. 이전 대화 맥락을 참고해서 답변하세요.
{duplicate_rule}

이전 대화:
{history_text}

임직원 데이터:
{context}

질문: {query}"""
    return session.sql(f"""
        SELECT SNOWFLAKE.CORTEX.COMPLETE(
            'claude-3-5-sonnet',
            $${prompt}$$
        ) AS answer
    """).collect()[0]["ANSWER"]

# ============================================================
# 메인 채팅 루프
# ============================================================

query = st.chat_input("예: AI 담당자 / DI팀 몇 명 / 그 팀 리스트 보여줘")

if query:
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.write(query)

    with st.chat_message("assistant"):
        with st.spinner("검색 중..."):

            detected_dept = resolve_dept(query)

            if is_count_search(query):
                count = get_count(dept=detected_dept)
                if detected_dept:
                    answer = f"{detected_dept} 임직원은 총 {count}명입니다."
                else:
                    answer = f"금호건설 전체 임직원은 총 {count}명입니다."
                st.write(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})

            elif is_list_all_search(query):
                count = get_count(dept=detected_dept)
                if count > MAX_LIST_COUNT and not detected_dept:
                    answer = (
                        f"전체 임직원이 {count}명으로 한번에 조회하기 어렵습니다.\n\n"
                        "아래 중 하나를 특정해 주시면 안내해드릴게요.\n"
                        "- 팀/부서명 (예: DI팀, 인사총무팀)\n"
                        "- 담당업무 (예: AI, 그룹웨어, 재무)\n"
                        "- 직위 (예: 매니저, 수석매니저)\n"
                        "- 이름"
                    )
                    st.write(answer)
                    st.session_state.messages.append({"role": "assistant", "content": answer})
                else:
                    rows = sql_list(dept=detected_dept)
                    if not rows:
                        answer = "데이터가 없습니다."
                        st.write(answer)
                        st.session_state.messages.append({"role": "assistant", "content": answer})
                    else:
                        df = rows_to_dataframe(rows, is_dict=False)
                        label = f"{detected_dept} " if detected_dept else "전체 "
                        st.write(f"{label}임직원 총 {len(df)}명입니다.")
                        st.dataframe(df, use_container_width=True)
                        st.session_state.messages.append({"role": "assistant", "content": df})

            elif is_number_search(query):
                rows = sql_number_search(query)
                if not rows:
                    answer = "해당 번호로 검색된 임직원이 없습니다."
                    st.write(answer)
                    st.session_state.messages.append({"role": "assistant", "content": answer})
                else:
                    has_duplicate = check_duplicate_name(rows, is_dict=False)
                    context = rows_to_context(rows, is_dict=False)
                    answer = ask_llm(context, query, has_duplicate)
                    st.write(answer)
                    st.session_state.messages.append({"role": "assistant", "content": answer})

            else:
                results = cortex_search(query)
                if not results:
                    answer = "검색 결과가 없습니다."
                    st.write(answer)
                    st.session_state.messages.append({"role": "assistant", "content": answer})
                else:
                    has_duplicate = check_duplicate_name(results, is_dict=True)
                    context = rows_to_context(results, is_dict=True)
                    answer = ask_llm(context, query, has_duplicate)
                    st.write(answer)
                    st.session_state.messages.append({"role": "assistant", "content": answer})