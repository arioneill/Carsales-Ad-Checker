@echo off
echo ============================================
echo  carsales Ad Checker — Push to GitHub
echo ============================================
echo.
echo Paste the repository URL from GitHub.
echo It looks like: https://github.com/YOUR-NAME/carsales-ad-checker.git
echo.
set /p REPO_URL="GitHub repo URL: "
echo.
cd /d "C:\Users\ethan.ravenhall\Code\carsales-ad-checker"
git remote add origin %REPO_URL%
git push -u origin master
echo.
if %errorlevel%==0 (
    echo SUCCESS! Your app is now on GitHub.
    echo Next step: go to share.streamlit.io to deploy.
) else (
    echo Something went wrong. Check the URL and try again.
)
echo.
pause
