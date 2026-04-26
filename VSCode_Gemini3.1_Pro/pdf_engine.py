import fitz  # PyMuPDF
import os

class PDFEngine:
    @staticmethod
    def get_pages_images(filepath, zoom=0.5):
        """指定したPDFの各ページ画像（ピクセルデータ）とインデックスをリストで取得します。"""
        images = []
        try:
            doc = fitz.open(filepath)
            for page_index in range(len(doc)):
                page = doc.load_page(page_index)
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                images.append(
                    {
                        "filepath": filepath,
                        "page_index": page_index,
                        "image_bytes": pix.tobytes("png"), # PNG bytes for easy Qt loading
                        "width": pix.width,
                        "height": pix.height,
                    }
                )
            doc.close()
        except Exception as e:
            print(f"Error loading {filepath}: {e}")
        return images

    @staticmethod
    def build_pdf_from_pages(page_data_list, output_path):
        """ページデータのリスト（filepath, page_index）から新しいPDFを生成します。"""
        new_doc = fitz.open()
        
        # 開いているドキュメントのキャッシュ（ループ内での重複オープンを防ぐ）
        open_docs = {}
        for pd in page_data_list:
            fp = pd["filepath"]
            idx = pd["page_index"]
            if fp not in open_docs:
                open_docs[fp] = fitz.open(fp)
            
            new_doc.insert_pdf(open_docs[fp], from_page=idx, to_page=idx)
            
        new_doc.save(output_path)
        new_doc.close()
        
        for doc in open_docs.values():
            doc.close()

    @staticmethod
    def split_pdf_to_pages(page_data_list, output_dir, base_name="page"):
        """ページデータのリストをそれぞれ個別のPDFファイルとして分割保存します。"""
        open_docs = {}
        for i, pd in enumerate(page_data_list):
            fp = pd["filepath"]
            idx = pd["page_index"]
            if fp not in open_docs:
                open_docs[fp] = fitz.open(fp)
                
            out_doc = fitz.open()
            out_doc.insert_pdf(open_docs[fp], from_page=idx, to_page=idx)
            
            out_path = os.path.join(output_dir, f"{base_name}_{i+1:03d}.pdf")
            out_doc.save(out_path)
            out_doc.close()

        for doc in open_docs.values():
            doc.close()
