import re
import os
import json
import time
import traceback
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect, TimeoutError

def wait_for_element_with_retry(page, locator, description, timeout_seconds=10, max_attempts=3):
    """尝试等待元素出现，如果超时则返回False，成功则返回True"""
    for attempt in range(max_attempts):
        try:
            print(f"等待{description}，第{attempt + 1}次尝试...")
            page.locator(locator).wait_for(state="visible", timeout=timeout_seconds * 1000)
            print(f"✓ {description} 已找到!")
            return True
        except Exception as e:
            print(f"✗ 等待{description}超时: {e}")
            if attempt < max_attempts - 1:
                print("准备重试...")
            else:
                print(f"已达到最大尝试次数({max_attempts})，无法找到{description}")
                return False
    return False

def refresh_page_and_wait(page, url, refresh_attempts=5, total_wait_time=120):
    """刷新页面并等待指定元素，总共尝试指定次数"""
    start_time = time.time()
    elapsed_time = 0
    refresh_count = 0
    
    web_button_found = False
    starting_server_found = False
    
    while elapsed_time < total_wait_time and refresh_count < refresh_attempts:
        if not (web_button_found and starting_server_found):
            print(f"刷新页面，第{refresh_count + 1}次尝试...")
            try:
                page.goto(url, timeout=30000)
                page.wait_for_load_state("domcontentloaded", timeout=60000)
                page.wait_for_load_state("networkidle", timeout=60000)
            except Exception as e:
                print(f"页面刷新或加载失败: {e}，但将继续执行")
            
            refresh_count += 1
        
        if not web_button_found:
            try:
                web_button_selector = "#iframe-container iframe >> nth=0"
                frame = page.frame_locator(web_button_selector)
                web_button = frame.get_by_text("Web", exact=True)
                if web_button:
                    time.sleep(20)  # 等待 iframe 稳定
                    print("找到Web按钮，点击...")
                    web_button.click()
                    web_button_found = True
                else:
                    print("未找到Web按钮")
            except Exception as e:
                print(f"查找或点击Web按钮失败: {e}")
        
        if web_button_found and not starting_server_found:
            try:
                time.sleep(3)  # 等待Web按钮响应
                starting_server_selector = "#iframe-container iframe >> nth=0"
                iframe_chain = page.frame_locator(starting_server_selector)
                
                try:
                    inner_frame = iframe_chain.frame_locator("iframe[name=\"ded0e382-bedf-478d-a870-33bb6cadac6f\"]")
                    web_frame = inner_frame.frame_locator("iframe[title=\"Web\"]")
                    preview_frame = web_frame.frame_locator("#previewFrame")
                    starting_server = preview_frame.get_by_role("heading", name="Starting server")
                    if starting_server:
                        print("找到Starting server文本")
                        starting_server_found = True
                    else:
                        print("未找到Starting server文本")
                except Exception as e:
                    print(f"通过嵌套iframe查找Starting server失败: {e}")
                
                if not starting_server_found:
                    for frame in page.frames:
                        try:
                            heading = frame.get_by_role("heading", name="Starting server")
                            if heading:
                                print("通过框架搜索找到Starting server文本")
                                starting_server_found = True
                                break
                        except:
                            continue
            except Exception as e:
                print(f"查找Starting server失败: {e}")
        
        if web_button_found and starting_server_found:
            print("Web按钮和Starting server文本都已找到")
            break
        
        time.sleep(5)
        elapsed_time = time.time() - start_time
        print(f"已等待 {int(elapsed_time)} 秒，剩余 {int(total_wait_time - elapsed_time)} 秒")
    
    return web_button_found and starting_server_found

def run(playwright: Playwright) -> None:
    google_pw = os.getenv("GOOGLE_PW", "")
    credentials = google_pw.split(' ', 1) if google_pw else []
    email = credentials[0] if len(credentials) > 0 else None
    password = credentials[1] if len(credentials) > 1 else None
    app_url = os.getenv("APP_URL", "https://idx.google.com/app-43646734")
    cookies_path = Path("google_cookies.json")
    
    if not email or not password:
        print("错误: 缺少凭据。请设置 GOOGLE_PW 环境变量，格式为 '邮箱 密码'。")
        print("例如: export GOOGLE_PW='your.email@gmail.com your_password'")
        return
    
    try:
        # GitHub Actions 需要 --no-sandbox 以避免权限问题
        browser = playwright.firefox.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context()
        
        cookies_loaded = False
        if cookies_path.exists():
            try:
                print("尝试使用已保存的 cookies 登录...")
                with open(cookies_path, 'r') as f:
                    cookies = json.load(f)
                context.add_cookies(cookies)
                cookies_loaded = True
            except Exception as e:
                print(f"加载 cookies 失败: {e}，将尝试密码登录...")
                cookies_loaded = False
        
        page = context.new_page()
        
        try:
            print(f"导航到 {app_url}")
            try:
                page.goto(app_url, timeout=30000)
            except Exception as e:
                print(f"页面加载超时: {e}")
            
            login_required = True
            current_url = page.url
            if cookies_loaded:
                if "idx.google.com" in current_url and "signin" not in current_url:
                    print("已通过 cookies 登录成功!")
                    login_required = False
                else:
                    print("Cookie 登录失败，将尝试密码登录...")
            
            if login_required:
                print("开始密码登录流程...")
                if "signin" not in page.url:
                    try:
                        page.goto(app_url, timeout=60000)
                        page.wait_for_load_state("domcontentloaded", timeout=60000)
                        page.wait_for_load_state("networkidle", timeout=60000)
                    except Exception as e:
                        print(f"加载登录页面失败: {e}，但将继续执行")
                
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                    choose_account = page.query_selector('text="Choose an account"')
                    if choose_account:
                        print("检测到'选择账户'页面，尝试选择账户...")
                        try:
                            email_account = page.get_by_text(email)
                            if email_account:
                                print(f"找到邮箱账户，点击...")
                                email_account.click()
                                page.wait_for_load_state("networkidle", timeout=10000)
                            else:
                                email_div = page.query_selector(f'div:has-text("{email}")')
                                if email_div:
                                    print(f"找到邮箱 div，点击...")
                                    email_div.click()
                                    page.wait_for_load_state("networkidle", timeout=10000)
                                else:
                                    first_account = page.query_selector('.OVnw0d')
                                    if first_account:
                                        print("彼此Ladder" not found: .OVnw0d')
                                        first_account.click()
                                        page.wait_for_load_state("networkidle", timeout=10000)
                                    else:
                                        print("未找到账户选项，将继续尝试...")
                        except Exception as e:
                            print(f"选择账户失败: {e}，但将继续执行")
                    else:
                        print("未检测到'选择账户'页面，继续正常登录流程...")
                        
                        try:
                            print("输入邮箱...")
                            email_field = page.get_by_label("Email or phone") or page.query_selector('input[type="email"]')
                            if email_field:
                                email_field.fill(email)
                            else:
                                print("未找到邮箱输入框，但将继续执行")
                            
                            next_button = page.get_by_role("button", name="Next") or page.query_selector('button[jsname="LgbsSe"]')
                            if next_button:
                                next_button.click()
                            else:
                                print("未找到下一步按钮，但将继续执行")
                        except Exception as e:
                            print(f"邮箱输入失败: {e}，但将继续执行")
                
                try:
                    page.wait_for_selector('input[type="password"]', state="visible", timeout=20000)
                    print("密码输入框已出现")
                except:
                    print("等待密码输入框超时，但将继续尝试")
                
                print("输入密码...")
                try:
                    password_field = page.get_by_label("Enter your password") or page.query_selector('input[type="password"]')
                    if password_field:
                        password_field.fill(password)
                    else:
                        print("未找到密码输入框，但将继续执行")
                    
                    next_button = page.get_by_role("button", name="Next") or page.query_selector('button[jsname="LgbsSe"]')
                    if next_button:
                        next_button.click()
                        print("提交密码")
                        time.sleep(5)
                    else:
                        print("未找到密码页面的下一步按钮，但将继续执行")
                except Exception as e:
                    print(f"密码输入失败: {e}，但将继续执行")
                
                try:
                    page.goto(app_url, timeout=30000)
                except:
                    print(f"跳转到目标页面失败，但将继续执行")
                
                current_url = page.url
                if "idx.google.com" in current_url and "signin" not in current_url:
                    print("密码登录成功!")
                    try:
                        print("保存 cookies...")
                        cookies = context.cookies()
                        with open(cookies_path, 'w') as f:
                            json.dump(cookies, f)
                    except Exception as e:
                        print(f"保存 cookies 失败: {e}，但将继续执行")
                else:
                    print(f"登录可能失败，当前 URL: {current_url}，但将继续执行")
            
            print(f"导航到 {app_url}")
            try:
                page.goto(app_url, timeout=30000)
            except:
                print(f"跳转到 {app_url} 失败，但将继续执行")
            
            current_url = page.url
            print(f"当前 URL: {current_url}")
            if "idx.google.com" in current_url and "signin" not in current_url:
                try:
                    print("保存最终 cookies...")
                    cookies = context.cookies()
                    with open(cookies_path, 'w') as f:
                        json.dump(cookies, f)
                    print("Cookies 保存成功!")
                except Exception as e:
                    print(f"保存最终 cookies 失败: {e}，但将继续执行")
                
                print("成功访问目标页面!")
                elements_found = refresh_page_and_wait(page, app_url, refresh_attempts=5, total_wait_time=120)
                if elements_found:
                    print("成功点击 Web 按钮并找到 Starting server，等待 20 秒...")
                    time.sleep(20)
                else:
                    print("在 120 秒内未能找到 Web 按钮或 Starting server")
            else:
                print(f"警告: 当前页面 URL 与目标不匹配: {current_url}")
            
        except Exception as e:
            print(f"页面交互错误: {e}")
            print(f"错误详情: {traceback.format_exc()}")
        finally:
            print("自动化流程完成!")
    except Exception as e:
        print(f"浏览器初始化错误: {e}")
        print(f"错误详情: {traceback.format_exc()}")
    finally:
        try:
            page.close()
        except:
            pass
        try:
            context.close()
        except:
            pass
        try:
            browser.close()
        except:
            pass
        print("脚本执行完毕!")

if __name__ == "__main__":
    try:
        with sync_playwright() as playwright:
            run(playwright)
    except Exception as e:
        print(f"Playwright 启动失败: {e}")
        print(f"错误详情: {traceback.format_exc()}")
        print("脚本终止")
