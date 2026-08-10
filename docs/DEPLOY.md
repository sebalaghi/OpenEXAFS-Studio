# Deployment

## A. Publish the repository from Windows

The easiest route is to double-click:

`PUBLISH_TO_GITHUB.bat`

Requirements:

- Git for Windows
- GitHub CLI (`gh`)
- access to the `sebalaghi` GitHub account

The script creates or updates the public repository `sebalaghi/OpenEXAFS-Studio`, enables GitHub Pages with workflow deployment through the GitHub API, and triggers the Pages workflow.

## B. GitHub Pages

The repository contains `.github/workflows/pages.yml`. It publishes the static landing page from
`site/` whenever `main` is updated.

The publish script attempts to enable Pages automatically. If your GitHub CLI token does not have Pages/administration write permission, open repository **Settings > Pages**, set the source to **GitHub Actions** once, and re-run the Pages workflow.

Expected Pages address after deployment:

`https://sebalaghi.github.io/OpenEXAFS-Studio/`

Important: GitHub Pages is static hosting. It displays the project website and documentation but does
not execute Python, XrayLarch, or Feff8L.

## C. Browser-running application with Streamlit Community Cloud

1. Push this repository to GitHub.
2. Sign in to Streamlit Community Cloud with GitHub.
3. Create a new app.
4. Repository: `sebalaghi/OpenEXAFS-Studio`
5. Branch: `main`
6. Entry point: `streamlit_app.py`
7. Deploy.

The web app depends on the host allowing the Feff8L native executable that comes with the Larch
installation. If Feff8L cannot execute on the hosted platform, path generation must be performed in the
desktop edition and the resulting `feffNNNN.dat` files can still be used locally for Larch fitting.

## D. Local Streamlit test

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-web.txt
streamlit run streamlit_app.py
```
