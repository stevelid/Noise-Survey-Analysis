@echo off
setlocal
cd /d "G:\My Drive\Programing\Noise Survey Analysis"
set "CONFIG=G:\Shared drives\Venta\Jobs\5931 Lains Shooting School, Quarley\5931 Surveys\March\noise_survey_config_5931_march.json"
set "STDOUT=G:\My Drive\Programing\Noise Survey Analysis\output\manual-test-5931\server-stdout.log"
set "STDERR=G:\My Drive\Programing\Noise Survey Analysis\output\manual-test-5931\server-stderr.log"
del "%STDOUT%" 2>nul
del "%STDERR%" 2>nul
start "NSA5931" /b python -m bokeh serve noise_survey_analysis --port 5007 --allow-websocket-origin localhost:5007 --args --config "%CONFIG%" --control-port 8765 1>"%STDOUT%" 2>"%STDERR%"
