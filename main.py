import os
import json
import time
import traceback
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright

def wait_for_element(page, selector, description, timeout=20000, retries=3):
    """等待元素出现，成功返回 True，失败返回 False"""
    for i in range(retries):
        try:
            print(f"等待 {description}，第 {i+1}/{retries} 次...")
            page.locator(selector).wait_for(state="visible", timeout=timeout)
            print(f"✓ {description} 已找到")
            return True
        except Exception as e:
            print(f"✗ 等待 {description} 失败: {e}")
            time.sleep(1)
    print(f"✗ 无法找到 {description}")
    return False

def refresh_page_and_wait(page, url, max_attempts=5, total_wait=120):
    """刷新页面并等待 Web 按钮和 Starting server"""
    start_time = time.time()
    web_found = False
    server_found = False

    for attempt in range(max_attempts):
        if time.time() - start_time > total_wait:
            print("超时，停止尝试")
            break
        print(f"刷新页面，第 {attempt+1}/{max_attempts} 次...")
        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
        except Exception as e:
            print(f"页面加载失败: {e}")

        # 查找 Web 按钮
        if not web_found:
            web_selector = "button:has-text('Web'), a:has-text('Web')"
            if wait_for_element(page, web_selector, "Web 按钮", timeout=15000):
                try:
                    page.locator(web_selector).click()
                    print("✓ Web 按钮已点击")
                    web_found = True
                    time.sleep(5)  # 等待响应
                except Exception as e:
                    print(f"点击 Web 按钮失败: {e}")

        # 查找 Starting server
        if web_found and not server_found:
            server_selector = "h1, h2, h3, div:has-text('Starting server')"
            if wait_for_element(page, server_selector, "Starting server", timeout=30000):
                server_found = True
                print("✓ Starting server 已找到")

        if web_found and server_found:
            print("✓ Web 按钮和 Starting server 已找到")
            break
        time.sleep(5)

    return web_found and server_found

def run(playwright: Playwright):
    # 获取环境变量
    google_pw = os.getenv("GOOGLE_PW", "")
    credentials = google_pw.split(" ", 1) if google_pw else []
    email = credentials[0] if credentials else None
    password = credentials[1] if len(credentials) > 1 else None
    app_url = os.getenv("APP_URL", "https://idx.google.com/app-43646734")
    cookies_path = Path("google_cookies.json")

    # 验证凭据
    if not email or not password:
        print("错误: GOOGLE_PW 格式应为 '邮箱 密码'")
        raise ValueError("GOOGLE_PW 缺失或格式错误")

    browser = None
    context = None
    page = None
    try:
        # 启动浏览器
        browser = playwright.firefox.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context()
        page = context.new_page()

        # 加载 Cookies
        cookies_loaded = False
        if cookies_path.exists():
            try:
                with open(cookies_path, "r") as f:
                    cookies = json.load(f)
                # 过滤有效 Cookies
                valid_cookies = [
                    c for c in cookies
                    if not c.get("expires") or c["expires"] == -1 or c["expires"] > time.time()
                ]
                if valid_cookies:
                    context.add_cookies(valid_cookies)
                    cookies_loaded = True
                    print("✓ Cookies 加载成功")
                else:
                    print("Cookies 已过期或无效")
            except Exception as e:
                print(f"加载 Cookies 失败: {e}")

        # 访问 APP_URL
        print(f"导航到 {app_url}")
        try:
            page.goto(app_url, wait_until="networkidle", timeout=60000)
        except Exception as e:
            print(f"页面加载失败: {e}")
        current_url = page.url
        print(f"当前 URL: {current_url}")

        # 检查是否需要登录
        login_required = "signin" in current_url or "accounts.google.com" in current_url
        if cookies_loaded and not login_required:
            print("✓ 通过 Cookies 登录成功")
        else:
            print("需要密码登录...")

            # 检测 CAPTCHA
            captcha_selector = "img[src*='captcha'], div[id*='captcha'], div:has-text('CAPTCHA')"
            if wait_for_element(page, captcha_selector, "CAPTCHA", timeout=5000):
                print("⚠ 检测到 CAPTCHA")
                page.screenshot(path="captcha_screenshot.png")
                raise RuntimeError("CAPTCHA 阻止登录")

            # 输入邮箱
            email_selector = "input[type='email'], input[aria-label='Email or phone']"
            if wait_for_element(page, email_selector, "邮箱输入框", timeout=30000):
                page.locator(email_selector).fill(email)
                print("✓ 邮箱已输入")
                next_selector = "button:has-text('Next'), button[aria-label*='Next']"
                if wait_for_element(page, next_selector, "下一步按钮", timeout=15000):
                    page.locator(next_selector).click()
                    print("✓ 点击下一步")
                else:
                    raise RuntimeError("未找到下一步按钮")

            # 输入密码
            password_selector = "input[type='password'], input[aria-label='Enter your password']"
            if wait_for_element(page, password_selector, "密码输入框", timeout=30000):
                page.locator(password_selector).fill(password)
                print("✓ 密码已输入")
                if wait_for_element(page, next_selector, "下一步按钮", timeout=15000):
                    page.locator(next_selector).click()
                    print("✓ 提交密码")
                    time.sleep(5)  # 等待登录完成
                else:
                    raise RuntimeError("未找到密码页面的下一步按钮")
            else:
                raise RuntimeError("未找到密码输入框")

            # 验证登录
            try:
                page.goto(app_url, wait_until="networkidle", timeout=60000)
            except Exception as e:
                print(f"重定向到 {app_url} 失败: {e}")
            current_url = page.url
            print(f"登录后 URL: {current_url}")
            if "idx.google.com" in current_url and "signin" not in current_url:
                print("✓ 登录成功")
                # 保存 Cookies
                cookies = context.cookies()
                with open(cookies_path, "w") as f:
                    json.dump(cookies, f)
                print("✓ Cookies 保存成功")
            else:
                print(f"⚠ 登录失败，当前 URL: {current_url}")
                page.screenshot(path="login_failed_screenshot.png")
                raise RuntimeError("登录失败")

        # 执行页面操作
        if refresh_page_and_wait(page, app_url, max_attempts=5, total_wait=120):
            print("✓ 成功点击 Web 按钮并找到 Starting server")
            time.sleep(20)  # 等待操作完成
            # 保存最终 Cookies
            cookies = context.cookies()
            with open(cookies_path, "w") as f:
                json.dump(cookies, f)
            print("✓ 最终 Cookies 保存成功")
        else:
            print("⚠ 未找到 Web 按钮或 Starting server")
            page.screenshot(path="operation_failed_screenshot.png")
            raise RuntimeError("页面操作失败")

        # 保存截图
        page.screenshot(path="screenshot.png")
        print("✓ 截图保存到 screenshot.png")

    except Exception as e:
        print(f"错误: {e}")
        print(f"错误详情: {traceback.format_exc()}")
        raise
    finally:
        if page:
            page.close()
        if context:
            context.close()
        if browser:
            browser.close()
        print("脚本执行完毕")

if __name__ == "__main__":
    try:
        with sync_playwright() as playwright:
            run(playwright)
    except Exception as e:
        print(f"Playwright 启动失败: {e}")
        print(f"错误详情: {traceback.format_exc()}")
        exit(1)
