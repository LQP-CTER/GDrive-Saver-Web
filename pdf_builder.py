"""
PDF Builder module — assembles extracted page images into a high-quality PDF.
Supports both lossless (img2pdf) and Pillow-based assembly methods.
"""

import os
import io
from typing import List, Optional

from PIL import Image

import config
from utils import log_info, log_success, log_warning, log_error, log_progress, format_size


class PDFBuilder:
    """Assembles page images into a high-quality PDF document."""
    
    @staticmethod
    def build_pdf(
        images: List[bytes],
        output_path: str,
        dpi: int = None,
        quality: int = None
    ) -> Optional[str]:
        """
        Build a PDF from a list of page images (as bytes).
        
        Args:
            images: List of image data in bytes (PNG or JPEG)
            output_path: Full path for the output PDF file
            dpi: Resolution in dots per inch (default from config)
            quality: JPEG quality 1-100 (default from config)
        
        Returns:
            Path to the created PDF file, or None on failure
        """
        if not images:
            log_error("No images provided to build PDF")
            return None
        
        dpi = dpi or config.IMAGE_DPI
        quality = quality or config.IMAGE_QUALITY
        
        log_info(f"Building PDF from {len(images)} pages...")
        log_info(f"Output: {output_path}")
        log_info(f"Settings: DPI={dpi}, Quality={quality}")
        
        # Try img2pdf first (lossless, fastest)
        result = PDFBuilder._build_with_img2pdf(images, output_path)
        if result:
            return result
        
        # Fallback: Use Pillow
        log_info("Falling back to Pillow-based PDF assembly...")
        return PDFBuilder._build_with_pillow(images, output_path, dpi, quality)
    
    @staticmethod
    def _build_with_img2pdf(images: List[bytes], output_path: str) -> Optional[str]:
        """
        Build PDF using img2pdf (lossless — no re-encoding).
        This produces the highest quality output as it embeds images directly.
        """
        try:
            import img2pdf
            
            # Convert any non-JPEG/PNG images to PNG first
            processed_images = []
            for i, img_data in enumerate(images):
                try:
                    # Validate the image
                    img = Image.open(io.BytesIO(img_data))
                    
                    # img2pdf works best with JPEG and PNG
                    if img.format not in ('JPEG', 'PNG'):
                        # Convert to PNG
                        buf = io.BytesIO()
                        img.save(buf, format='PNG')
                        processed_images.append(buf.getvalue())
                    else:
                        processed_images.append(img_data)
                    
                    log_progress(i + 1, len(images), "  Processing:")
                    
                except Exception as e:
                    log_warning(f"Skipping invalid image {i + 1}: {e}")
            
            if not processed_images:
                return None
            
            # Build PDF with img2pdf
            # Use A4-like layout that adapts to image aspect ratio
            pdf_bytes = img2pdf.convert(processed_images)
            
            with open(output_path, 'wb') as f:
                f.write(pdf_bytes)
            
            file_size = os.path.getsize(output_path)
            log_success(f"PDF created successfully! Size: {format_size(file_size)}")
            return output_path
            
        except ImportError:
            log_warning("img2pdf not available, using alternative method")
            return None
        except Exception as e:
            log_warning(f"img2pdf failed: {e}")
            return None
    
    @staticmethod
    def _build_with_pillow(
        images: List[bytes],
        output_path: str,
        dpi: int,
        quality: int
    ) -> Optional[str]:
        """
        Build PDF using Pillow.
        Slightly lower quality than img2pdf but more compatible.
        """
        try:
            pil_images = []
            
            for i, img_data in enumerate(images):
                try:
                    img = Image.open(io.BytesIO(img_data))
                    
                    # Convert to RGB if necessary (PDF doesn't support RGBA)
                    if img.mode == 'RGBA':
                        # Create white background
                        bg = Image.new('RGB', img.size, (255, 255, 255))
                        bg.paste(img, mask=img.split()[3])
                        img = bg
                    elif img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    pil_images.append(img)
                    log_progress(i + 1, len(images), "  Processing:")
                    
                except Exception as e:
                    log_warning(f"Skipping invalid image {i + 1}: {e}")
            
            if not pil_images:
                log_error("No valid images to create PDF")
                return None
            
            # Save as PDF
            first_img = pil_images[0]
            remaining = pil_images[1:] if len(pil_images) > 1 else []
            
            save_kwargs = {
                "format": "PDF",
                "resolution": float(dpi),
                "save_all": True,
                "append_images": remaining,
                "quality": quality,
            }
            
            first_img.save(output_path, **save_kwargs)
            
            file_size = os.path.getsize(output_path)
            log_success(f"PDF created successfully! Size: {format_size(file_size)}")
            return output_path
            
        except Exception as e:
            log_error(f"Pillow PDF creation failed: {e}")
            return None
    
    @staticmethod
    def save_individual_images(
        images: List[bytes],
        output_dir: str,
        prefix: str = "page",
        fmt: str = None
    ) -> List[str]:
        """
        Save each page image as an individual file.
        
        Args:
            images: List of image data in bytes
            output_dir: Directory to save images in
            prefix: Filename prefix
            fmt: Image format (PNG or JPEG)
        
        Returns:
            List of saved file paths
        """
        fmt = fmt or config.IMAGE_FORMAT
        ext = "png" if fmt.upper() == "PNG" else "jpg"
        
        os.makedirs(output_dir, exist_ok=True)
        saved_paths = []
        
        for i, img_data in enumerate(images):
            try:
                img = Image.open(io.BytesIO(img_data))
                
                # Convert RGBA to RGB for JPEG
                if fmt.upper() == "JPEG" and img.mode == 'RGBA':
                    bg = Image.new('RGB', img.size, (255, 255, 255))
                    bg.paste(img, mask=img.split()[3])
                    img = bg
                elif img.mode != 'RGB' and fmt.upper() == "JPEG":
                    img = img.convert('RGB')
                
                filename = f"{prefix}_{i + 1:03d}.{ext}"
                filepath = os.path.join(output_dir, filename)
                
                save_kwargs = {}
                if fmt.upper() == "JPEG":
                    save_kwargs["quality"] = config.IMAGE_QUALITY
                    save_kwargs["optimize"] = True
                
                img.save(filepath, format=fmt.upper(), **save_kwargs)
                saved_paths.append(filepath)
                
                log_progress(i + 1, len(images), "  Saving:")
                
            except Exception as e:
                log_warning(f"Failed to save image {i + 1}: {e}")
        
        if saved_paths:
            total_size = sum(os.path.getsize(p) for p in saved_paths)
            log_success(f"Saved {len(saved_paths)} images ({format_size(total_size)})")

        return saved_paths

    @staticmethod
    def _add_long_content(story, text: str, style, max_chunk: int = 5000):
        """Add long text content to story, splitting into chunks with page breaks."""
        escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        paragraphs = escaped.split("\n\n")
        current_chunk = []
        current_len = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(para) > max_chunk:
                if current_chunk:
                    story.append(Paragraph("\n".join(current_chunk), style))
                    current_chunk = []
                    current_len = 0

                for i in range(0, len(para), max_chunk):
                    chunk = para[i:i + max_chunk]
                    story.append(Paragraph(chunk, style))
                    story.append(Spacer(1, 4))
                continue

            if current_len + len(para) > max_chunk and current_chunk:
                story.append(Paragraph("\n".join(current_chunk), style))
                story.append(Spacer(1, 4))
                current_chunk = []
                current_len = 0

            current_chunk.append(para)
            current_len += len(para)

        if current_chunk:
            story.append(Paragraph("\n".join(current_chunk), style))

    @staticmethod
    def build_report_pdf(
        scraped_data,
        output_path: str,
        include_images: bool = True,
        max_images: int = 10,
    ) -> Optional[str]:
        """
        Build a structured PDF report from scraped website data.

        Args:
            scraped_data: ScrapedPage object from scraper module
            output_path: Full path for the output PDF file
            include_images: Whether to include images in the report
            max_images: Maximum number of images to include per item

        Returns:
            Path to the created PDF file, or None on failure
        """
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import mm, cm
            from reportlab.lib.colors import HexColor
            from reportlab.platypus import (
                SimpleDocTemplate, Paragraph, Spacer, Image,
                PageBreak, Table, TableStyle, KeepTogether, HRFlowable
            )
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
            from reportlab.lib import colors
        except ImportError:
            log_warning("reportlab not available, falling back to Pillow-based report")
            return PDFBuilder._build_report_with_pillow(scraped_data, output_path, include_images, max_images)

        try:
            doc = SimpleDocTemplate(
                output_path,
                pagesize=A4,
                topMargin=2.5*cm,
                bottomMargin=2*cm,
                leftMargin=2*cm,
                rightMargin=2*cm,
            )

            styles = getSampleStyleSheet()

            styles.add(ParagraphStyle(
                name="ReportTitle",
                parent=styles["Title"],
                fontSize=22,
                textColor=HexColor("#1e293b"),
                spaceAfter=4,
                alignment=TA_CENTER,
                fontName="Helvetica-Bold",
            ))

            styles.add(ParagraphStyle(
                name="ReportSubtitle",
                parent=styles["Normal"],
                fontSize=10,
                textColor=HexColor("#64748b"),
                spaceAfter=12,
                alignment=TA_CENTER,
                fontName="Helvetica",
            ))

            styles.add(ParagraphStyle(
                name="SectionHeader",
                parent=styles["Heading2"],
                fontSize=14,
                textColor=HexColor("#334155"),
                spaceBefore=16,
                spaceAfter=8,
                fontName="Helvetica-Bold",
                borderWidth=0,
                borderColor=HexColor("#e2e8f0"),
                borderPadding=4,
            ))

            styles.add(ParagraphStyle(
                name="ItemTitle",
                parent=styles["Heading3"],
                fontSize=12,
                textColor=HexColor("#4f46e5"),
                spaceBefore=10,
                spaceAfter=4,
                fontName="Helvetica-Bold",
            ))

            styles.add(ParagraphStyle(
                name="BodyText2",
                parent=styles["BodyText"],
                fontSize=9.5,
                textColor=HexColor("#334155"),
                alignment=TA_JUSTIFY,
                leading=14,
                spaceAfter=6,
            ))

            styles.add(ParagraphStyle(
                name="MetaLabel",
                parent=styles["Normal"],
                fontSize=8,
                textColor=HexColor("#94a3b8"),
                fontName="Helvetica-Oblique",
                spaceAfter=2,
            ))

            styles.add(ParagraphStyle(
                name="MetaValue",
                parent=styles["Normal"],
                fontSize=8.5,
                textColor=HexColor("#475569"),
                spaceAfter=6,
            ))

            styles.add(ParagraphStyle(
                name="UrlText",
                parent=styles["Normal"],
                fontSize=8,
                textColor=HexColor("#6366f1"),
                spaceAfter=4,
                fontName="Helvetica",
            ))

            story = []

            story.append(Spacer(1, 12))
            story.append(Paragraph("WEBSITE SCRAPE REPORT", styles["ReportTitle"]))
            story.append(Spacer(1, 4))
            story.append(Paragraph(scraped_data.page_title or scraped_data.source_url, styles["ReportSubtitle"]))

            divider = HRFlowable(width="100%", thickness=1.5, color=HexColor("#6366f1"), spaceAfter=12)
            story.append(divider)

            meta_data = [
                ["Source:", scraped_data.source_url],
                ["Scraped at:", scraped_data.scrape_time],
                ["Items found:", str(scraped_data.stats.get("total_items", 0))],
                ["Images found:", str(scraped_data.stats.get("total_images", 0))],
            ]
            if scraped_data.page_description:
                meta_data.insert(2, ["Description:", scraped_data.page_description])

            meta_table = Table(
                [[Paragraph(k, styles["MetaLabel"]), Paragraph(v, styles["MetaValue"])] for k, v in meta_data],
                colWidths=[3.5*cm, 12*cm],
            )
            meta_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
            ]))
            story.append(meta_table)
            story.append(Spacer(1, 8))

            if scraped_data.main_content:
                story.append(Paragraph("MAIN CONTENT", styles["SectionHeader"]))
                story.append(divider)
                PDFBuilder._add_long_content(story, scraped_data.main_content, styles["BodyText2"], max_chunk=8000)

            if scraped_data.items:
                story.append(PageBreak())
                story.append(Paragraph(f"CONTENT ITEMS ({len(scraped_data.items)})", styles["SectionHeader"]))
                story.append(divider)

                for i, item in enumerate(scraped_data.items):
                    item_story = []
                    item_story.append(Paragraph(item.title, styles["ItemTitle"]))

                    if item.url:
                        item_story.append(Paragraph(item.url, styles["UrlText"]))

                    if item.text:
                        text_preview = item.text[:500]
                        item_story.append(Paragraph(text_preview, styles["BodyText2"]))

                    if include_images and item.images:
                        for img_data in item.images[:max_images]:
                            try:
                                img = Image(io.BytesIO(img_data))
                                img.drawWidth = min(12*cm, A4[0] - 4*cm)
                                img.drawHeight = img.drawWidth * (img.imageHeight / max(img.imageWidth, 1))
                                if img.drawHeight > 10*cm:
                                    img.drawHeight = 10*cm
                                    img.drawWidth = img.drawHeight * (img.imageWidth / max(img.imageHeight, 1))
                                item_story.append(Spacer(1, 6))
                                item_story.append(img)
                                item_story.append(Spacer(1, 6))
                            except Exception:
                                pass

                    story.append(KeepTogether(item_story))

                    if i < len(scraped_data.items) - 1:
                        story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor("#e2e8f0"), spaceAfter=8))

            if include_images and scraped_data.all_images:
                story.append(PageBreak())
                story.append(Paragraph(f"IMAGES ({len(scraped_data.all_images)})", styles["SectionHeader"]))
                story.append(divider)

                imgs = scraped_data.all_images[:max_images * 2]
                for idx in range(0, len(imgs), 2):
                    row_imgs = []
                    for j in range(2):
                        if idx + j < len(imgs):
                            try:
                                img = Image(io.BytesIO(imgs[idx + j]))
                                img.drawWidth = 7.5*cm
                                img.drawHeight = img.drawWidth * (img.imageHeight / max(img.imageWidth, 1))
                                if img.drawHeight > 8*cm:
                                    img.drawHeight = 8*cm
                                    img.drawWidth = img.drawHeight * (img.imageWidth / max(img.imageHeight, 1))
                                row_imgs.append(img)
                            except Exception:
                                row_imgs.append(Paragraph("", styles["Normal"]))
                        else:
                            row_imgs.append(Paragraph("", styles["Normal"]))
                    img_table = Table([row_imgs], colWidths=[7.5*cm, 7.5*cm])
                    img_table.setStyle(TableStyle([
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ]))
                    story.append(img_table)

            story.append(Spacer(1, 20))
            story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#cbd5e1"), spaceAfter=8))
            story.append(Paragraph(
                f"Generated by GDrive Saver — {scraped_data.scrape_time}",
                ParagraphStyle("Footer", parent=styles["Normal"], fontSize=7, textColor=HexColor("#94a3b8"), alignment=TA_CENTER),
            ))

            doc.build(story)
            file_size = os.path.getsize(output_path)
            log_success(f"Report PDF created! Size: {format_size(file_size)}")
            return output_path

        except Exception as e:
            log_warning(f"reportlab report failed: {e}")
            return PDFBuilder._build_report_with_pillow(scraped_data, output_path, include_images, max_images)

    @staticmethod
    def _build_report_with_pillow(scraped_data, output_path: str, include_images: bool, max_images: int) -> Optional[str]:
        """Fallback: Build a simple image-based report using Pillow (no text formatting)."""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import cm
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        except ImportError:
            log_error("reportlab required for report generation. Install with: pip install reportlab")
            return None

        try:
            doc = SimpleDocTemplate(
                output_path,
                pagesize=A4,
                topMargin=2*cm,
                bottomMargin=2*cm,
                leftMargin=2*cm,
                rightMargin=2*cm,
            )
            styles = getSampleStyleSheet()
            story = []

            title_style = ParagraphStyle("RptTitle", parent=styles["Title"], fontSize=18, spaceAfter=6)
            body_style = ParagraphStyle("RptBody", parent=styles["Normal"], fontSize=10, spaceAfter=6)

            story.append(Paragraph("WEBSITE SCRAPE REPORT", title_style))
            story.append(Paragraph(scraped_data.page_title or scraped_data.source_url, body_style))
            story.append(Paragraph(f"Source: {scraped_data.source_url}", body_style))
            story.append(Paragraph(f"Scraped at: {scraped_data.scrape_time}", body_style))
            story.append(Paragraph(f"Items: {scraped_data.stats.get('total_items', 0)} | Images: {scraped_data.stats.get('total_images', 0)}", body_style))

            if scraped_data.main_content:
                story.append(Spacer(1, 12))
                PDFBuilder._add_long_content(story, scraped_data.main_content, body_style, max_chunk=8000)

            if scraped_data.items:
                story.append(PageBreak())
                for item in scraped_data.items:
                    story.append(Paragraph(item.title, styles["Heading3"]))
                    if item.url:
                        story.append(Paragraph(item.url, body_style))
                    if item.text:
                        story.append(Paragraph(item.text[:400], body_style))
                    story.append(Spacer(1, 8))

            if include_images and scraped_data.all_images:
                story.append(PageBreak())
                for img_data in scraped_data.all_images[:max_images * 2]:
                    try:
                        img = Image(io.BytesIO(img_data))
                        img.drawWidth = 14*cm
                        img.drawHeight = img.drawWidth * (img.imageHeight / max(img.imageWidth, 1))
                        story.append(img)
                        story.append(Spacer(1, 8))
                    except Exception:
                        pass

            doc.build(story)
            file_size = os.path.getsize(output_path)
            log_success(f"Report PDF created (fallback)! Size: {format_size(file_size)}")
            return output_path

        except Exception as e:
            log_error(f"Pillow report fallback failed: {e}")
            return None
