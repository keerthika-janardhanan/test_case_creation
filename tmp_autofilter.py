from openpyxl import Workbook

wb = Workbook()
ws = wb.active
ws.append(["sl", "Action"])
ws.append([1, "Log into Oracle"])
ws.append([2, "Navigate"])
ws.auto_filter.ref = "A1:B3"
ws.auto_filter.add_filter_column(1, ["(?"], blank=False)

wb.save("tmp_autofilter.xlsx")
