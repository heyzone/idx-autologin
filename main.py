import re
import os
import json
import time
import traceback
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, TimeoutError

def wait_for_element_with_retry(page, selector, description, timeout_seconds=10, max_attempts=3):
    """尝试等待元素出现，成功返回 True，失败返回 False"""
    for attempt in range(max_attempts):
        try:
            print(f"等待 {description}，第 {attempt + 1}/{max_attempts} 次尝试...")
            page.locator(selector).wait_for(state="visible", timeout=timeout_seconds * 1000)
            print(f"✓ {description} 已找到")
            return True
        except Exception as e:
            print(f"✗ 等待 {description} 超时: {e}")
            if attempt < max_attempts - 1:
                print("准备重试...")
            time.sleep(1)
    print(f"✗ 达到最大尝试次数 ({max_attempts})，无法找到 {description}")
    return False

def refresh_page_and_wait(page, url, refresh_attempts=5, total_wait_time=120):
    """刷新页面并等待 Web 按钮和 Starting server 文本"""
    start_time = time.time()
    refresh_count = 0
    web_button_found = False
    starting_server_found = False

    while time.time() - start_time < total_wait_time and refresh_count < refresh_attempts:
        if not (web_button_found and starting_server_found):
            print(f"刷新页面，第 {refresh_count + 1}/{refresh_attempts} 次尝试...")
            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
            except Exception as e:
                print(f"页面加载失败: {e}")
            
            refresh_count += 1

        # 查找 Web 按钮
        if not web_button_found:
            web_button_selector = "button:has-text('Web')"  # 简化选择器
            if wait_for_element_with_retry(page, web_button_selector, "Web 按钮", timeout_seconds=10):
                try:
                    page.locator(web_button_selector).click()
                    print("✓ Web 按钮已点击")
                    web_button_found = True
                    time.sleep(5)  # 等待响应
                except Exception as e:
                    print(f"点击 Web 按钮失败: {e}")

        # 查找 Starting server 文本
        if web_button_found and not starting_server_found:
            starting_server_selector = "h1, h2, h3, div:has-text('Starting server')"
            if wait_for_element_with_retry(page, starting_server_selector, "Starting server 文本", timeout_seconds=20):
                starting_server_found = True
                print("✓ Starting server 文本已找到")

        if web_button_found and starting_server_found:
            print("✓ Web 按钮和 Starting server 文本都已找到")
            break

        time.sleep(5)
        elapsed_time = time.time() - start_time
        print(f"已等待 {int(elapsed_time)} 秒，剩余 {int(total_wait_time - elapsed_time)} 秒")

    return web_button_found and starting_server_found

def run(playwright: Playwright) -> None:
    google_pw = os.getenv("GOOGLE_PW", "")
    credentials = google_pw.split(" ", 1) if google_pw else []
    email = credentials[0] if len(credentials) > 0 else None
    password = credentials[1] if len(credentials) > 1 else None
    app_url = os.getenv("APP_URL", "https://idx.google.com/app-43646734")
    cookies_path = Path("google_cookies.json")

    if not email or not password:
        print("错误: 缺少 GOOGLE_PW 环境变量（格式: '邮箱 密码'）")
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
                print("加载 google_cookies.json...")
                with open(cookies_path, "r") as f:
                    cookies = json.load(f)
                # 验证 Cookies 有效性（检查过期时间）
                current_time = time.time()
                valid_cookies = [
                    c for c in cookies
                    if not c.get("expires") or c["expires"] == -1 or c["expires"] > current_time
                ]
                if valid_cookies:
                    context.add_cookies(valid_cookies)
                    cookies_loaded = True
                    print("✓ Cookies 加载成功")
                else:
                    print("Cookies 已过期或无效，将尝试密码登录")
            except Exception as e:
                print(f"加载 Cookies 失败: {e}")

        # 访问 APP_URL
        print(f"导航到 {app_url}")
        page.goto(app_url, wait_until="networkidle", timeout=60000)
        current_url = page.url
        print(f"当前 URL: {current_url}")

        # 检查是否需要登录
        login_required = "signin" in current_url or "accounts.google.com" in current_url
        if cookies_loaded and not login_required:
            print("✓ 通过 Cookies 登录成功")
        else:
            print("需要密码登录...")

        # 登录流程
        if login_required:
            # 检测 CAPTCHA
            captcha_selector = "img[src*='captcha'], div[id*='captcha'], div:has-text('CAPTCHA')"
            if wait_for_element_with_retry(page, captcha_selector, "CAPTCHA", timeout_seconds=5):
                print("⚠ 检测到 CAPTCHA，可能阻止自动化登录")
                raise RuntimeError("CAPTCHA 检测到，需手动验证")

            # 输入邮箱
            email_selector = "input[type='email'], input[aria-label='Email or phone']"
            if wait_for_element_with_retry(page, email_selector, "邮箱输入框", timeout_seconds=20):
                page.locator(email_selector).fill(email)
                print("✓ 邮箱已输入")
                next_button_selector = "button:has-text('Next'), button[jsname='LgbsSe']"
                if wait_for_element_with_retry(page, next_button_selector, "下一步按钮", timeout_seconds=10):
                    page.locator(next_button_selector).click()
                    print("✓ 点击下一步")

            # 输入密码
            password_selector = "input[type='password'], input[aria-label='Enter your password']"
            if wait_for_element_with_retry(page, password_selector, "密码输入框", timeout_seconds=20):
                page.locator(password_selector).fill(password)
                print("✓ 密码已输入")
                if wait_for_element_with_retry(page, next_button_selector, "下一步按钮", timeout_seconds=10):
                    page.locator(next_button_selector).click()
                    print("✓ 提交密码")
                    time.sleep(5)  # 等待登录完成

            # 验证登录
            page.goto(app_url, wait_until="networkidle", timeout=60000)
            current_url = page.url
            print(f"登录后 URL: {current_url}")
            if "idx.google.com" in current_url and "signin" not in current_url:
                print("✓ 密码登录成功")
                # 保存 Cookies
                cookies = context.cookies()
                with open(cookies_path, "w") as f:
                    json.dump(cookies, f)
                print("✓ Cookies 保存成功")
            else:
                print(f"⚠ 登录失败，当前 URL: {current_url}")
                raise RuntimeError("登录失败")

        # 执行页面操作
        elements_found = refresh_page_and_wait(page, app_url, refresh_attempts=5, total_wait_time=120)
        if elements_found:
            print("✓ 成功点击 Web 按钮并找到 Starting server")
            time.sleep(20)  # 等待操作完成
        else:
            print("⚠ 未找到 Web 按钮或 Starting server")
            raise RuntimeError("页面操作失败")

        # 保存截图用于调试
        screenshot_path = Path("screenshot.png")
        page.screenshot(path=screenshot_path)
        print(f"✓ 截图保存到 {screenshot_path}")

    except Exception as e:
        print(f"错误: {e}")
        print(f"错误详情: {traceback.format_exc()}")
        raise  # 抛出异常，让 GitHub Actions 标记失败
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
        exit(1)  # 明确退出码，确保 GitHub Actions 检测失败
