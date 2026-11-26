import json, re, sys
from playwright.sync_api import sync_playwright, expect

TARGETS={"local":"http://127.0.0.1:8501","public":"https://3dnwbbikdupgrxq7ivmp8r.streamlit.app/"}
def check(browser,url):
    report={"url":url,"steps":[]}
    page=browser.new_page(viewport={"width":1600,"height":1000},accept_downloads=True)
    try:
        response=page.goto(url,wait_until="domcontentloaded",timeout=90000)
        report["http_status"]=response.status if response else None
        report["final_url"]=page.url.split("?")[0]
        wake=page.get_by_role("button",name=re.compile("Yes, get this app back up|Wake up|Get this app back up",re.I))
        if wake.count():
            wake.first.click(); report["steps"].append("Wake request")
        for name in ("Risk panosu","İşlem listesi","Vaka detayı","Research Lab"):
            nav=page.locator(".st-key-main_navigation").get_by_text(name,exact=False).first
            nav.wait_for(timeout=90000)
            nav.click(timeout=15000)
            page.wait_for_timeout(2500)
            if page.get_by_test_id("stException").count():raise AssertionError("Streamlit exception")
            report["steps"].append(name)
        expect(page.get_by_text("Berka | Doğrulanmış gerçek veri deneyi",exact=True)).to_be_visible(timeout=20000)
        expect(page.get_by_text("1.056.320",exact=True).first).to_be_visible(timeout=20000)
        with page.expect_download(timeout=15000) as download:
            page.get_by_role("button",name="Doğrulanmış karşılaştırma CSV").click()
        path=download.value.path()
        raw=path.read_text(encoding="utf-8-sig")
        assert "validated" in raw or "Geri bildirimli" in raw
        report["steps"].append("Research CSV verified")
        expect(page.get_by_text("South German Credit | Bağımsız yöntem tekrarı",exact=True)).to_be_visible(timeout=20000)
        with page.expect_download(timeout=15000) as external:
            page.get_by_role("button",name="Bağımsız deney CSV").click()
        import csv,io
        records=list(csv.DictReader(io.StringIO(external.value.path().read_text(encoding="utf-8-sig"))))
        assert len(records)==4 and all(sum(int(row[k]) for k in ("tp","fp","fn","tn"))==1000 for row in records)
        assert any(row["tp"]=="110" and row["fp"]=="148" for row in records)
        report["steps"].append("External CSV verified")
        expect(page.get_by_text("Gerçek bankacılık verisi | 9 kontrol senaryosu",exact=True)).to_be_visible(timeout=20000)
        with page.expect_download(timeout=15000) as controls:
            page.get_by_role("button",name="Tüm kontrol sonuçları CSV").click()
        cr=list(csv.DictReader(io.StringIO(controls.value.path().read_text(encoding="utf-8-sig"))))
        assert len(cr)==36 and len({row["scenario"] for row in cr})==9
        assert all(sum(int(row[k]) for k in ("tp","fp","fn","tn"))==int(row["n"]) for row in cr)
        report["steps"].append("36 control results CSV verified")
        report["success"]=True
    except Exception as e:
        report["success"]=False
        report["error"]=type(e).__name__
        report["details"]=str(e)[:600]
    finally:
        report["final_url"]=page.url.split("?")[0]
        report["title"]=page.title()
        if not report.get("success"):
            try:
                report["page_excerpt"]=page.locator("body").inner_text(timeout=3000)[:800]
                page.screenshot(path=("public" if url.startswith("https:") else "local")+"-failure.png")
            except Exception:pass
        page.close()
    return report
def main():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        reports={k:check(browser,v) for k,v in TARGETS.items()}
        browser.close()
    with open("e2e-results.json","w") as f:json.dump(reports,f,ensure_ascii=False,indent=2)
    print("E2E_RESULTS",json.dumps(reports,ensure_ascii=False),flush=True)
    if not all(v["success"] for v in reports.values()):sys.exit(1)
if __name__=="__main__":main()
