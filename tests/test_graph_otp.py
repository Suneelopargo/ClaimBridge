from app.graph.graph_mail_client import GraphMailClient


def main():
    client = GraphMailClient()
    otp = client.read_latest_otp()
    print("OTP =", otp)


if __name__ == "__main__":
    main()