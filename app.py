"""Root entrypoint for Streamlit: redirects cleanly to apps.dashboard.app."""

from apps.dashboard.app import main

if __name__ == "__main__":
    main()
