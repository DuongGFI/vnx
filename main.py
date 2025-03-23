from fastapi import FastAPI, HTTPException, Response
from playwright.sync_api import sync_playwright
import pandas as pd
import time
from io import StringIO

app = FastAPI()

def handle_popup(page):
    try:
        page.wait_for_load_state('networkidle')
        popup = page.wait_for_selector("text=Lưu ý về TPDN riêng lẻ", timeout=5000)
       
        if popup:
            checkboxes = page.query_selector_all('input[name="checkConfirm"]')
            for checkbox in checkboxes:
                if not checkbox.is_checked():
                    checkbox.check()
            time.sleep(2)
            approve_button = page.query_selector('#approvePopup, button:has-text("Đồng ý")')
            if approve_button:
                approve_button.click()
                print('Clicked popup')
            page.wait_for_selector('.popup-terms, #popupTerms, #cookieConsent', state='hidden', timeout=5000)
        else:
            print('No popup')
    except:
        print('Error in popup')
        pass

def set_items_per_page(page):
    try:
        dropdown = page.wait_for_selector('#slChangeNumberRecord_1', timeout=5000)
        dropdown.select_option(value="100")
        page.wait_for_load_state('networkidle')
        print('Select 100')
        time.sleep(2)
    except:
        pass

def scrape_data(n_pages=1):
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--single-process'
            ]
        )
        page = browser.new_page()
        page.goto("https://cbonds.hnx.vn/to-chuc-phat-hanh/thong-tin-phat-hanh")
        
        # Trang web có thể chặn bot từ máy chủ Render. Để kiểm tra:
        user_agent = page.evaluate("() => navigator.userAgent")
        print(f"User Agent: {user_agent}")      
        
        handle_popup(page)
        set_items_per_page(page)
  
        all_data = []
        # for current_page in range(1, n_pages + 1):
        #     page.wait_for_selector("#tbReleaseResult")
        #     table_data = page.evaluate("""
        #         () => {
        #             return Array.from(document.querySelectorAll('#tbReleaseResult tbody tr'))
        #                 .map(row => Array.from(row.querySelectorAll('td')).map(cell => cell.innerText));
        #         }
        #     """)
        #     all_data.extend(table_data)
        #     next_button = page.query_selector('a.next')
        #     if next_button:
        #         next_button.click()
        #         time.sleep(2)
        #     else:
        #         break
        for current_page in range(1, n_pages + 1):
            max_retries = 2
            retry_count = 0
            success = False
            
            while retry_count <= max_retries and not success:
                try:
                    # Thêm timeout động theo số lần retry
                    timeout = 30000 * (retry_count + 1)
                    
                    # Chờ bảng với các điều kiện nghiêm ngặt hơn
                    page.wait_for_selector(
                        "#tbReleaseResult:not(:empty)", 
                        state="attached", 
                        timeout=timeout
                    )
                    
                    # Verify có dữ liệu thực sự
                    table = page.query_selector("#tbReleaseResult")
                    rows = table.query_selector_all("tbody tr")
                    if len(rows) == 0:
                        raise Exception("Empty table detected")
                        
                    # Lấy dữ liệu
                    table_data = page.evaluate("""() => {
                        return Array.from(document.querySelectorAll('#tbReleaseResult tbody tr'))
                            .map(row => {
                                const cells = Array.from(row.querySelectorAll('td'));
                                return cells.map(cell => {
                                    const text = cell.innerText;
                                    const link = cell.querySelector('a')?.href;
                                    return link ? `${text} [LINK:${link}]` : text;
                                });
                            });
                    }""")
                    
                    all_data.extend(table_data)
                    success = True
                    
                except Exception as e:
                    print(f"Attempt {retry_count + 1} failed: {str(e)}")
                    retry_count += 1
                    
                    # Recovery actions
                    if retry_count <= max_retries:
                        print("Performing recovery actions...")
                        # 1. Thử reload trang
                        page.reload()
                        # 2. Đợi các element quan trọng khác
                        page.wait_for_selector("body", timeout=10000)
                        # 3. Thử đóng popup lại
                        handle_popup(page)
                        # 4. Thử reset pagination
                        page.evaluate("""() => {
                            try {
                                document.querySelector('a.page-first').click();
                            } catch(e) {}
                        }""")
                        time.sleep(2 * retry_count)
        
            if not success:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to retrieve data after {max_retries} retries on page {current_page}"
                )
        
            # Xử lý phân trang với retry
            pagination_success = False
            for _ in range(max_retries + 1):
                next_button = page.query_selector('a.next:not(.disabled)')
                if not next_button:
                    break
                    
                try:
                    # Click bằng JavaScript để tránh issues với actionability
                    page.evaluate("(btn) => btn.click()", next_button)
                    
                    # Chờ confirm navigation
                    page.wait_for_selector(
                        f"a.page-number:has-text('{current_page + 1}')", 
                        timeout=20000
                    )
                    
                    # Verify page change
                    current_page += 1
                    pagination_success = True
                    break
                except Exception as e:
                    print(f"Pagination failed: {str(e)}, retrying...")
                    time.sleep(3)
                    
            if not pagination_success and current_page < n_pages:
                raise HTTPException(
                    status_code=500,
                    detail=f"Pagination failed on page {current_page}"
                )
        browser.close()
        
        columns = [
            "STT", "Ngày đăng tin", "Tên DN", "Mã TP", "Tiền tệ", "Kỳ hạn",
            "Ngày phát hành", "Ngày đáo hạn", "Kỳ hạn còn lại (ngày)",
            "Khối lượng", "Mệnh giá", "Loại hình trả lãi", "Loại lãi suất",
            "Phương thức thanh toán lãi", "Mua lại và hoán đổi",
            "Thị trường phát hành", "Lãi suất phát hành (%/năm)", "Tình trạng", "Văn bản đính kèm"
        ]
        df = pd.DataFrame(all_data, columns=columns)
        return df
        
@app.get("/")
def read_root():
    return {"status": "OK", "message": "Service is running"}
    
@app.get("/scrape")
def scrape(n_pages: int = 1):
    try:
        df = scrape_data(n_pages)
        output = StringIO()
        df.to_csv(output, index=False)
        response = Response(content=output.getvalue(), media_type="text/csv")
        response.headers["Content-Disposition"] = "attachment; filename=data.csv"
        print(f"Scraped {len(df)} rows")
        print(df.head())
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
