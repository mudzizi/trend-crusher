import os
import yaml
from dotenv import load_dotenv

# .env 파일 로드 (레거시 지원 및 환경 변수 우선 적용용)
load_dotenv()

# --- System Version ---
VERSION = "11.9.7"

def load_config():
    """
    YAML 파일을 로드하고 환경 변수로 필요한 부분을 덮어씌웁니다.
    config.yaml이 없으면 config.example.yaml을 기본값으로 사용합니다.
    """
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_path, "config.yaml")
    example_path = os.path.join(base_path, "config.example.yaml")

    # 1. YAML 파일 로드 (실제 설정 파일 우선, 없으면 예제 파일)
    target_path = config_path if os.path.exists(config_path) else example_path
    
    with open(target_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 2. 버전 강제 동기화
    config["VERSION"] = VERSION

    # 3. 환경 변수 (OS Environment)로 중요한 값들 덮어씌우기 (Secrets 등)
    env_mappings = {
        "BINANCE_API_KEY": "BINANCE_API_KEY",
        "BINANCE_SECRET": "BINANCE_SECRET",
        "TELEGRAM_TOKEN": "TELEGRAM_TOKEN",
        "TELEGRAM_CHAT_ID": "TELEGRAM_CHAT_ID",
        "DRY_RUN": "DRY_RUN",
        "SYMBOL": "SYMBOL",
        "SEED": "SEED"
    }

    for config_key, env_key in env_mappings.items():
        env_val = os.getenv(env_key)
        if env_val is not None:
            # 타입 변환 처리
            if config_key == "DRY_RUN":
                config[config_key] = env_val.lower() == "true"
            elif config_key == "SEED":
                config[config_key] = float(env_val)
            else:
                config[config_key] = env_val

    return config

# 전역 CONFIG 객체 생성
CONFIG = load_config()

# 레거시 코드 호환을 위한 VERSION 전역 변수 유지
VERSION = CONFIG["VERSION"]
