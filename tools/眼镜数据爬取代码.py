# 爬取拼多多眼镜商品数据（需安装requests、BeautifulSoup）
import requests
from bs4 import BeautifulSoup
import csv

def crawl_pdd_glasses():
    url = "https://search.pinduoduo.com/search?q=%E7%9C%BC%E9%95%9C&page=1"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")
    
    glasses_list = []
    # 提取商品信息（需根据拼多多页面结构调整，此处为示例）
    items = soup.find_all("div", class_="goods-item")
    for i, item in enumerate(items[:20]):  # 取前20款
        try:
            title = item.find("div", class_="goods-title").text.strip()
            # 简单判断镜框形状（根据标题关键词）
            if "方形" in title:
                frame_shape = "方形"
            elif "圆形" in title:
                frame_shape = "圆形"
            elif "鹅蛋" in title:
                frame_shape = "鹅蛋形"
            else:
                frame_shape = "长方形"
            price = item.find("div", class_="goods-price").text.strip()
            glasses_list.append([
                f"pdd_{i+1}", frame_shape, "52-18-140", "TR90", 
                "-10.00", "-1.00", "1.60", price, 
                item.find("img")["src"] if item.find("img") else "https://default-img.com"
            ])
        except Exception as e:
            print(f"爬取失败：{e}")
    
    # 保存为CSV
    with open("pdd_glasses_data.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["glasses_id", "frame_shape", "frame_size", "frame_material", 
                        "lens_degree_min", "lens_degree_max", "lens_refractive_index", "price", "image_url"])
        writer.writerows(glasses_list)
    print("爬取完成，已保存到pdd_glasses_data.csv")

if __name__ == "__main__":
    crawl_pdd_glasses()