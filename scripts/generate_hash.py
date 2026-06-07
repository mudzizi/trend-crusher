from werkzeug.security import generate_password_hash
import sys

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/generate_hash.py <your_password>")
        return

    password = sys.argv[1]
    # Using scrypt which is modern and secure
    hashed = generate_password_hash(password, method='scrypt')
    print(f"\nPassword: {password}")
    print(f"Hash: {hashed}\n")
    print("Copy the Hash above into your config.yaml under DASHBOARD_PASSWORD_HASH")

if __name__ == "__main__":
    main()
