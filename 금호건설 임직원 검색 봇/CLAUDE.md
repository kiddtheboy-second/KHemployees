# 금호건설 임직원 검색 봇

## 프로젝트 개요
Snowflake Cortex Search + Streamlit으로 만든 임직원 검색 챗봇.

## Snowflake 환경
- Account: ACCOUNTADMIN 역할
- Database: CONSTRUCTION_RAG
- Schema: DOCS
- Warehouse: COMPUTE_WH

## 주요 테이블
- employees: 전체 임직원 1308명 (JSON 162개 파일에서 적재)
- employees_raw: 원본 JSON VARIANT 테이블

## Cortex Search
- 서비스명: employees_search
- 검색 컬럼: search_text (이름 + 담당업무 합친 컬럼)
- LLM: claude-3-5-sonnet

## 현재 검색 기능
1. 이름 검색: SQL LIKE 직접 조회
2. 번호 검색: 4자리 이상 숫자 감지 → SQL LIKE
3. 부서 리스트: DB에서 부서명 감지 → 필터링
4. 인원수 조회: 부서 감지 후 COUNT
5. 전체 리스트: 50명 초과 시 범위 좁히기 요청
6. 텍스트 검색: Cortex Search (의미 기반)
7. 대화 히스토리: 최근 6턴 LLM에 전달
8. 직전 부서 기억: session_state.last_dept

## 파일 구조
- streamlit_app.py: 메인 Streamlit 앱
- GitHub 레포: https://github.com/kiddtheboy-second/KHemployees
- Snowflake Streamlit 앱명: 금호건설 임직원 검색 봇

## 현재 알려진 이슈
- 이름 직접 검색 시 Cortex Search가 못 찾는 경우 있음
  → extract_korean_name()으로 SQL 직접 조회로 분기 처리 중
- APJ 리전이라 claude-3-7-sonnet 이상 모델은 cross-region 설정 필요

## 다음 작업 예정
- 이름 검색 정확도 개선
- 부서별 필터링 고도화
- PDF 공사 사례 문서 RAG 파이프라인 연동