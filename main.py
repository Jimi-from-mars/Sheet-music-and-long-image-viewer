import os
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import json
import winreg
import threading
import time

class ImageViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("乐谱/长图浏览器")
        
        # 设置全屏
        self.root.state('zoomed')
        
        # 配置文件路径
        self.setup_file = "setup.ini"
        
        # 配置键名定义
        self.CONFIG_KEYS = {
            'LAST_FILE': 'LastFile',
            'TREE_WIDTH': 'TreeWidth',
            'MASK_STATE': 'MaskEnabled',
            'FAVORITES': 'Favorites',
            'FAVORITES_POS': 'FavoritesManagerPos'
        }
        
        # 添加遮罩控制变量，并从配置文件加载上次的状态
        self.show_mask = tk.BooleanVar()
        try:
            config = self.load_config()
            self.show_mask.set(bool(int(config.get(self.CONFIG_KEYS['MASK_STATE'], '0'))))
        except:
            self.show_mask.set(False)
        
        # 创建菜单栏
        self.create_menu()
        
        # 配置文件名
        self.config_filename = "image_config.json"
        
        # 创建主框架
        self.main_frame = tk.Frame(root, bg='white')
        self.main_frame.pack(fill='both', expand=True)
        
        # 左侧目录树框架
        self.tree_frame = tk.Frame(self.main_frame, bg='white')
        self.tree_frame.pack(side='left', fill='y')
        
        # 创建一个内部框架来包含目树
        self.inner_tree_frame = tk.Frame(self.tree_frame, bg='white')
        self.inner_tree_frame.pack(fill='both', expand=True)
        
        # 左侧目录树
        self.tree = ttk.Treeview(self.inner_tree_frame, style='Custom.Treeview')
        self.tree.pack(fill='both', expand=True)
        self.tree.heading('#0', text='目录', anchor='w')
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)
        self.tree.bind("<Button-3>", self.on_right_click)  # 绑定右键点击事件
        
        # 创建自定义式
        style = ttk.Style()
        style.configure('Custom.Treeview', 
                       background='white',
                       fieldbackground='white',
                       borderwidth=0)  # 移除边框
        
        # 移除选中项的虚线框
        style.layout('Custom.Treeview', [
            ('Custom.Treeview.treearea', {'sticky': 'nswe'})
        ])
        
        #  - 使用简单的Frame
        self.sash = tk.Frame(
            self.main_frame,
            width=4,
            cursor='sb_h_double_arrow',
            bg='#4a90e2',  # 使用蓝色
            highlightthickness=0
        )
        self.sash.pack(side='left', fill='y', anchor='w')
        
        # 绑定事件
        self.sash.bind('<B1-Motion>', self.adjust_tree_width)
        self.sash.bind('<Button-1>', self.start_resize)
        
        # 加载保存的树宽度
        try:
            config = self.load_config()
            tree_width = int(config.get(self.CONFIG_KEYS['TREE_WIDTH'], '200'))
        except (WindowsError, ValueError):
            tree_width = 200  # 默认宽度
        
        self.tree_frame.configure(width=tree_width)
        self.tree_frame.pack_propagate(False)  # 防止frame自动调整大小
        
        # 右侧框架（包含画布和滚动条）
        self.right_frame = tk.Frame(self.main_frame)
        self.right_frame.pack(side='left', fill='both', expand=True)
        
        # 右侧图片显示区域
        self.canvas = tk.Canvas(self.right_frame, bg='white')
        self.canvas.pack(side='top', fill='both', expand=True)
        
        # 水平滚动条
        self.scrollbar = tk.Scrollbar(self.right_frame, orient='horizontal', command=self.canvas.xview)
        self.scrollbar.pack(side='bottom', fill='x')
        self.canvas.configure(xscrollcommand=self.scrollbar.set)
        
        # 当前图片和缩放比例
        self.current_image = None
        self.scale = 1.0
        self.current_directory = None  # 初始化当前目录
        
        # 加载上次访问的目录
        self.load_last_directory()
        
        # 绑定键盘事件
        self.root.bind('<KeyPress-plus>', self.zoom_in)
        self.root.bind('<KeyPress-minus>', self.zoom_out)
        
        # 绑定鼠标中键滚动件
        self.canvas.bind("<Button-2>", self.toggle_mask)  # 中键点击切换遮罩
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)  # 鼠标轮事件
        
        # 绑定窗口大小变化事件
        self.root.bind("<Configure>", self.on_window_resize)
        
        # 绑定窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # 记录最后访问的目录
        self.last_visited_directory = None
        
        # 添加标志，用于控制关闭时是否保存目录
        self.save_directory_on_close = True
        
        # 配置加粗标记样式
        self.tree.tag_configure('favorite', font=('TkDefaultFont', 9, 'bold'))
        
        # 支持的图片格式
        self.IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.bmp')
        
        # 收藏夹管理器尺寸
        self.FAVORITES_DIALOG_SIZE = {
            'width': 500,
            'height': 400
        }
        
        # 配置参数
        self.CONFIG = {
            'default_tree_width': 200,
            'min_tree_width': 100,
            'max_favorites': 50,
            'retry_times': 5,
            'retry_interval': 200,
            'overlap_min': 0.05,
            'overlap_max': 0.3,
            'overlap_step': 0.05
        }
    
    def create_menu(self):
        """创建菜单栏"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # 创建收藏夹菜单
        self.favorites_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="收藏夹", menu=self.favorites_menu)
        self.favorites_menu.add_command(label="整理收藏夹", command=self.show_favorites_manager)
        
        # 创建排序菜单
        sort_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="排序", menu=sort_menu)
        sort_menu.add_command(label="时间倒序", command=lambda: self.sort_files("time_desc"))
        sort_menu.add_command(label="时间顺序", command=lambda: self.sort_files("time_asc"))
        sort_menu.add_command(label="名称倒序", command=lambda: self.sort_files("name_desc"))
        sort_menu.add_command(label="名称顺序", command=lambda: self.sort_files("name_asc"))
        
        # 添加遮罩选项
        menubar.add_checkbutton(label="遮罩", variable=self.show_mask, 
                              command=self.refresh_image)
        
        # 添加帮助菜单
        menubar.add_command(label="帮助", command=self.show_help)
        
        # 更新收藏夹菜单
        self.update_favorites_menu()
    
    def show_timed_message(self, message, seconds=3):
        """显示定时消息对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("提示")
        dialog.geometry("300x100")
        dialog.transient(self.root)
        
        label = tk.Label(dialog, text=message, pady=20)
        label.pack()
        
        def close_dialog():
            time.sleep(seconds)
            dialog.destroy()
        
        # 启动定时器线程
        threading.Thread(target=close_dialog, daemon=True).start()
    
    def load_config(self):
        """从配置文件加载设置"""
        config = {}
        try:
            if os.path.exists(self.setup_file):
                with open(self.setup_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if '=' in line:
                            key, value = line.strip().split('=', 1)
                            config[key] = value
        except Exception as e:
            print(f"加载配置文件出错: {e}")
        return config
    
    def save_config(self, key, value):
        """保存设置到配置文件"""
        try:
            # 读取现有配置
            config = self.load_config()
            
            # 更新配置
            config[key] = value
            
            # 保存有配置
            with open(self.setup_file, 'w', encoding='utf-8') as f:
                for k, v in config.items():
                    f.write(f"{k}={v}\n")
        except Exception as e:
            print(f"保存配置文件出错: {e}")
    
    def save_last_directory(self, directory):
        """保存最后访问的文件到配置文件"""
        try:
            # 如果是文件，直接保存文件路径
            if hasattr(self, 'current_file_path'):
                path = os.path.normpath(self.current_file_path)
            else:
                # 如果没有打开文件则保存目录
                path = os.path.normpath(directory)
            
            self.save_config(self.CONFIG_KEYS['LAST_FILE'], path)
        except Exception as e:
            print(f"无法保存最后访问的路径: {e}")
    
    def load_last_directory(self):
        """从配置文件加载最后访问的文件"""
        try:
            config = self.load_config()
            last_path = config.get(self.CONFIG_KEYS['LAST_FILE'], '')
            
            # 检查路径是否存在
            if not os.path.exists(last_path):
                last_path = ''
            
            # 首先填充根目录
            self.populate_root()
            
            # 如果是文件，直接打开它
            if os.path.isfile(last_path):
                self.display_image(last_path)
            
        except Exception as e:
            print(f"加载上次访问路径时出错: {e}")
            self.populate_root()
    
    def populate_root(self):
        # 清空树
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # 获取收藏列表
        favorites = self.get_favorites()
        
        # 添加驱动器
        if os.name == 'nt':  # Windows
            import win32api
            drives = win32api.GetLogicalDriveStrings().split('\000')[:-1]
            for drive in drives:
                try:
                    # 获取驱动器卷标
                    volume_name = win32api.GetVolumeInformation(drive)[0]
                    drive_text = f"{drive} ({volume_name})" if volume_name else drive
                    drive_node = self.tree.insert('', 'end', text=drive_text, values=(drive,))
                    # 如果是收藏的项目，添加加粗标记
                    if drive in favorites:
                        self.tree.item(drive_node, tags=('favorite',))
                    self.tree.insert(drive_node, 'end', text='')
                except:
                    # 如果无法获取卷标信息，仅显示盘符
                    drive_node = self.tree.insert('', 'end', text=drive, values=(drive,))
                    # 如果是收藏的项目，添加加粗标记
                    if drive in favorites:
                        self.tree.item(drive_node, tags=('favorite',))
                    self.tree.insert(drive_node, 'end', text='')
        else:  # Unix/Linux/Mac
            root_node = self.tree.insert('', 'end', text='/', values=('/'))
            if '/' in favorites:
                self.tree.item(root_node, tags=('favorite',))
            self.tree.insert(root_node, 'end', text='')
    
    def on_tree_open(self, event):
        node = self.tree.focus()
        
        # 删除所有有的节点
        children = self.tree.get_children(node)
        if children:
            # 检查临时节点
            if len(children) == 1 and self.tree.item(children[0])['text'] == '':
                self.tree.delete(children[0])
                self.populate_node(node)
    
    def populate_node(self, node):
        path = self.tree.item(node)['values'][0]
        favorites = self.get_favorites()
        
        # 获取排序方法
        sort_method = self.get_sort_method(path)
        
        try:
            items = os.listdir(path)
            
            # 获取文件和目录的完整信息
            file_info = []
            for item in items:
                full_path = os.path.join(path, item)
                try:
                    stat = os.stat(full_path)
                    file_info.append({
                        'name': item,
                        'path': full_path,
                        'is_dir': os.path.isdir(full_path),
                        'mtime': stat.st_mtime
                    })
                except (OSError, PermissionError):
                    continue
            
            # 根据排序方法排序
            if sort_method == 'time_desc':
                file_info.sort(key=lambda x: (-x['mtime'], x['name'].lower()))
            elif sort_method == 'time_asc':
                file_info.sort(key=lambda x: (x['mtime'], x['name'].lower()))
            elif sort_method == 'name_desc':
                file_info.sort(key=lambda x: x['name'].lower(), reverse=True)
            else:  # name_asc
                file_info.sort(key=lambda x: x['name'].lower())
            
            # 先添加子目录
            for info in file_info:
                if info['is_dir']:
                    try:
                        child = self.tree.insert(node, 'end', text=info['name'], values=(info['path'],))
                        if info['path'] in favorites:
                            self.tree.item(child, tags=('favorite',))
                        if os.listdir(info['path']):
                            self.tree.insert(child, 'end', text='')
                    except PermissionError:
                        continue
            
            # 再添加图片文件
            for info in file_info:
                if not info['is_dir'] and info['name'].lower().endswith(self.IMAGE_EXTENSIONS):
                    # 将时间戳转换为日期字符串，只显示年月日
                    mtime_str = time.strftime("%Y-%m-%d", time.localtime(info['mtime']))
                    # 在文件名后添加修改日期
                    display_name = f"{info['name']} ({mtime_str})"
                    
                    child = self.tree.insert(node, 'end', text=display_name, values=(info['path'],))
                    if info['path'] in favorites:
                        self.tree.item(child, tags=('favorite',))
        except PermissionError:
            pass
    
    def expand_to_path(self, path):
        """展开到指定路径"""
        try:
            if not os.path.exists(path):
                messagebox.showinfo("提示", "目录不存在")
                return
            
            # 标准化路径格式
            path = os.path.normpath(path)
            
            # 首先找到对应的驱动器节点
            drive = os.path.splitdrive(path)[0] + '\\'
            drive_node = None
            
            # 查找驱动器节点
            for item in self.tree.get_children(''):
                values = self.tree.item(item)['values']
                if values and values[0].upper() == drive.upper():
                    drive_node = item
                    break
            
            if drive_node:
                # 展开驱动器节点
                self.tree.item(drive_node, open=True)
                children = self.tree.get_children(drive_node)
                if children and self.tree.item(children[0])['text'] == '':
                    self.tree.delete(children[0])
                    self.populate_node(drive_node)
                
                # 获取剩余的路径部分
                remaining_path = path[len(drive):]
                if remaining_path:
                    parts = remaining_path.split('\\')
                    current = drive_node
                    
                    # 逐级展开目录
                    for part in parts:
                        if not part:  # 跳过空字符串
                            continue
                        found = False
                        for child in self.tree.get_children(current):
                            if self.tree.item(child)['text'] == part:
                                current = child
                                self.tree.item(child, open=True)
                                # 展开子节点
                                children = self.tree.get_children(child)
                                if children and self.tree.item(children[0])['text'] == '':
                                    self.tree.delete(children[0])
                                    self.populate_node(child)
                                found = True
                                break
                        if not found:
                            break
                    
                    # 选中最后的节点并展开
                    if current:
                        self.tree.selection_set(current)
                        self.tree.see(current)
                        self.tree.focus(current)
                        # 触发选择事件来展开目录
                        self.on_tree_select(None)
        except Exception as e:
            print(f"展开路径时出错: {e}")
    
    def on_tree_select(self, event):
        """处理目录树选择事件"""
        selected_item = self.tree.selection()[0]
        values = self.tree.item(selected_item)['values']
        if not values:  # 如果没有值，直接返回
            return
            
        file_path = values[0]  # 使用完整路径
        
        if os.path.isfile(file_path):
            self.display_image(file_path)
            self.last_visited_directory = os.path.dirname(file_path)
        else:
            # 如果是目录，切换展开/收拢状态
            self.last_visited_directory = file_path
            is_open = self.tree.item(selected_item, 'open')
            self.tree.item(selected_item, open=not is_open)
            
            if not is_open:  # 如果是展开操作
                children = self.tree.get_children(selected_item)
                if children and self.tree.item(children[0])['text'] == '':
                    self.tree.delete(children[0])
                    self.populate_node(selected_item)
    
    def display_image(self, file_path):
        self.current_image = Image.open(file_path)
        self.current_file_path = file_path  # 存当前文件路径
        self.load_image_config(file_path)  # 加载置
        self.show_image()
    
    def show_image(self):
        if self.current_image:
            width, height = self.current_image.size
            scaled_width = int(width * self.scale)
            scaled_height = int(height * self.scale)
            
            # 缩放图片
            image = self.current_image.resize(
                (scaled_width, scaled_height), 
                Image.Resampling.LANCZOS
            )
            
            # 清空画布
            self.canvas.delete("all")
            
            # 如果片高度超过画布高度，进行拆分显示
            canvas_height = self.canvas.winfo_height()
            if scaled_height > canvas_height:
                self.split_image(image, scaled_width, scaled_height, canvas_height)
            else:
                # 显示单个图片
                photo = ImageTk.PhotoImage(image)
                self.canvas.create_image(0, 0, anchor='nw', image=photo)
                self.canvas.image = photo  # 保持引用
    
    def split_image(self, image, width, height, canvas_height):
        # 计算需要的页面数
        overlap = int(canvas_height * self.overlap_ratio)  # 使用动态重叠比例
        effective_height = canvas_height - overlap
        num_pages = (height + effective_height - 1) // effective_height
        
        # 计算每个页面的宽度，为原始宽度加上边框空间
        page_width = width + 20  # 添加边框空间
        
        # 调整画布大小以容纳所有页面
        total_width = page_width * num_pages
        self.canvas.config(scrollregion=(0, 0, total_width, canvas_height))
        
        # 存所有的PhotoImage对象
        self.photo_images = []
        
        # 建遮罩图像（如果需要）
        if self.show_mask.get():
            # 创建一个纯半透明遮罩图像
            mask_color = (144, 238, 144, 25)  # 浅绿色，alpha=25 (90%透明)
            mask_image = Image.new('RGBA', (width, overlap), mask_color)  # 只创建重叠分高度的遮罩
            mask_photo = ImageTk.PhotoImage(mask_image)
            self.photo_images.append(mask_photo)  # 保持引用
        
        # 显示每个页面
        for i in range(num_pages):
            # 计算当前页面的起始位置
            start_y = i * (canvas_height - overlap)
            
            # 创建当前页面的图像
            page_height = min(canvas_height, height - start_y)
            page = image.crop((0, start_y, width, start_y + page_height))
            photo = ImageTk.PhotoImage(page)
            self.photo_images.append(photo)
            
            # 在画布上显示当前页面
            x = i * page_width + 10
            
            # 绘制漂亮的边框
            border_x = x - 5
            
            # 先画主边框
            self.canvas.create_rectangle(
                border_x, 5,
                border_x + width + 10, canvas_height - 5,
                outline='#4a90e2',
                width=2,
                dash=None
            )
            
            # 添加内阴影效果 - 所有页面都画完整的三边阴影
            # 边阴影
            self.canvas.create_line(
                border_x + 1, 6,
                border_x + width + 9, 6,
                fill='#2c3e50',
                width=1
            )
            
            # 左边阴影
            self.canvas.create_line(
                border_x + 1, 6,
                border_x + 1, canvas_height - 6,
                fill='#2c3e50',
                width=1
            )
            
            # 下边阴影 - 每一页画
            self.canvas.create_line(
                border_x + 1, canvas_height - 6,
                border_x + width + 9, canvas_height - 6,
                fill='#2c3e50',
                width=1
            )
            
            # 显示图片
            self.canvas.create_image(x, 10, anchor='nw', image=photo)
            
            # 如果启用了遮罩，添加半透明遮罩
            if self.show_mask.get():
                if i == 0:  # 第一页
                    # 在底部添加罩
                    self.canvas.create_image(
                        x, canvas_height - overlap + 10,  # 起点
                        anchor='nw',
                        image=mask_photo
                    )
                else:  # 其他页
                    # 在顶部添加遮罩
                    self.canvas.create_image(
                        x, 10,  # 起
                        anchor='nw',
                        image=mask_photo
                    )
                    
                    # 如果不是最后一页，底部也添加遮罩
                    if i < num_pages - 1:
                        self.canvas.create_image(
                            x, canvas_height - overlap + 10,  # 起点
                            anchor='nw',
                            image=mask_photo
                        )
            
            # 添加重叠部分的分隔线
            if i == 0:  # 第一页
                # 在底部画红线
                self.canvas.create_line(
                    x, canvas_height - overlap + 10,  # 起点
                    x + width, canvas_height - overlap + 10,  # 终点
                    fill='red',
                    width=1
                )
            else:  # 其他
                # 在顶部画红线
                self.canvas.create_line(
                    x, overlap + 10,  # 起点
                    x + width, overlap + 10,  # 终点
                    fill='red',
                    width=1
                )
                
                # 如果不是最后一页，在底部也画红线
                if i < num_pages - 1:
                    self.canvas.create_line(
                        x, canvas_height - overlap + 10,  # 起
                        x + width, canvas_height - overlap + 10,  # 终点
                        fill='red',
                        width=1
                    )
            
            # 添加码和重叠比例信息
            self.canvas.create_text(
                border_x + width/2 + 5,
                canvas_height - 20,
                text=f"第 {i+1}/{num_pages} 页 (重叠: {int(self.overlap_ratio*100)}%)",
                fill='#4a90e2',
                font=('Arial', 10)
            )
    
    def zoom_in(self, event):
        self.scale += 0.1
        self.show_image()
        if hasattr(self, 'current_file_path'):
            self.save_image_config(self.current_file_path)
    
    def zoom_out(self, event):
        self.scale = max(0.1, self.scale - 0.1)
        self.show_image()
        if hasattr(self, 'current_file_path'):
            self.save_image_config(self.current_file_path)
    
    def adjust_overlap(self, event):
        # 根据滚轮方调整重叠比例
        if event.delta > 0:
            self.overlap_ratio = min(0.3, self.overlap_ratio + 0.05)  # 最大30%重叠
        else:
            self.overlap_ratio = max(0.05, self.overlap_ratio - 0.05)  # 小5%重叠
        
        # 重新显示图片
        if self.current_image:
            self.show_image()
            self.save_image_config(self.current_file_path)  # 保存配置
    
    def on_window_resize(self, event):
        # 确保窗口的大小变化，而不是子组件的大小变化
        if event.widget == self.root:
            # 等待一小段时间后新显示图片，避免频繁刷新
            self.root.after_cancel(self.resize_timer) if hasattr(self, 'resize_timer') else None
            self.resize_timer = self.root.after(100, self.show_image)
    
    def load_image_config(self, file_path):
        """加载图片配置"""
        config_path = os.path.join(os.path.dirname(file_path), self.config_filename)
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                configs = json.load(f)
                image_name = os.path.basename(file_path)
                if image_name in configs:
                    config = configs[image_name]
                    self.scale = config.get('scale', 1.0)
                    self.overlap_ratio = config.get('overlap_ratio', 0.2)
        except (FileNotFoundError, json.JSONDecodeError):
            self.scale = 1.0
            self.overlap_ratio = 0.2
    
    def save_image_config(self, file_path):
        """保存图片配置"""
        config_path = os.path.join(os.path.dirname(file_path), self.config_filename)
        try:
            # 尝试加载现有配置
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    configs = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                configs = {}
            
            # 更新当前图片的配置
            image_name = os.path.basename(file_path)
            configs[image_name] = {
                'scale': self.scale,
                'overlap_ratio': self.overlap_ratio
            }
            
            # 保存配置
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(configs, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"无法保存配置件: {e}")
    
    def on_closing(self):
        """窗口关闭时的处理"""
        if self.save_directory_on_close:
            if hasattr(self, 'current_file_path'):
                # 如果有打开的文件，保存文件路径
                self.save_last_directory(self.current_file_path)
            elif self.last_visited_directory:
                # 如果没有打开文件但有访问的目录，保目录路径
                self.save_last_directory(self.last_visited_directory)
        self.root.destroy()
    
    def refresh_image(self):
        """刷新图显示"""
        if self.current_image:
            self.show_image()
            # 保存遮罩状态到配置文件
            try:
                self.save_config(self.CONFIG_KEYS['MASK_STATE'], str(int(self.show_mask.get())))
            except Exception as e:
                print(f"无法保存遮罩状态: {e}")
    
    def toggle_mask(self, event):
        """使用鼠标中键切换遮罩状态"""
        self.show_mask.set(not self.show_mask.get())
        self.refresh_image()
    
    def on_mouse_wheel(self, event):
        """处理鼠标滚轮事件"""
        if event.state & 4:  # 查是否按下了Control键
            # Control + 滚轮调整重叠比例
            if event.delta > 0:
                self.overlap_ratio = min(0.3, self.overlap_ratio + 0.05)
            else:
                self.overlap_ratio = max(0.05, self.overlap_ratio - 0.05)
            
            if self.current_image:
                self.show_image()
                if hasattr(self, 'current_file_path'):
                    self.save_image_config(self.current_file_path)
        else:
            # 普通滚轮控制横向滚动
            current = self.canvas.xview()
            if event.delta > 0:
                self.canvas.xview_moveto(current[0] - 0.1)  # 向左滚动
            else:
                self.canvas.xview_moveto(current[0] + 0.1)  # 向右滚动
    
    def start_resize(self, event):
        """开始调整大小时记初始位置"""
        self.start_x = event.x_root
        self.start_width = self.tree_frame.winfo_width()
    
    def adjust_tree_width(self, event):
        """调整树的宽度"""
        diff = event.x_root - self.start_x
        new_width = max(100, min(self.start_width + diff, 
                               self.root.winfo_width() - 100))
        self.tree_frame.configure(width=new_width)
        self.tree_frame.pack_propagate(False)
        
        # 保存新的宽度到配置文件
        try:
            self.save_config(self.CONFIG_KEYS['TREE_WIDTH'], str(new_width))
        except Exception as e:
            print(f"无法保存树宽度: {e}")
    
    def on_right_click(self, event):
        """处理右键点击事件"""
        item = self.tree.identify_row(event.y)
        if item:
            values = self.tree.item(item)['values']
            if not values:
                return
            
            path = values[0]
            favorites = self.get_favorites()
            
            if path in favorites:
                # 取消收藏
                favorites.remove(path)
                self.tree.item(item, tags=())  # 移除加粗标记
            else:
                # 添加收藏
                if len(favorites) >= 50:  # 修改为50个限制
                    messagebox.showinfo("提示", "收藏数量已达到50个限制，请先删除一些收藏")
                    return
                favorites.append(path)
                self.tree.item(item, tags=('favorite',))  # 添加加粗标记
            
            self.save_favorites(favorites)
            self.update_favorites_menu()
    
    def get_favorites(self):
        """从配置文件获取收藏列表"""
        try:
            config = self.load_config()
            favorites_str = config.get(self.CONFIG_KEYS['FAVORITES'], '[]')
            return json.loads(favorites_str)
        except Exception:
            return []
    
    def save_favorites(self, favorites):
        """保存收藏列表到配置文件"""
        try:
            self.save_config(self.CONFIG_KEYS['FAVORITES'], json.dumps(favorites))
        except Exception as e:
            messagebox.showerror("错误", f"无法保存收藏: {e}")
    
    def update_favorites_menu(self):
        """更新收藏夹菜单"""
        # 清空现有菜单项(保留整理收藏夹选)
        for i in range(1, self.favorites_menu.index('end') + 1):
            self.favorites_menu.delete(1)
        
        # 获取收藏列表
        favorites = self.get_favorites()
        
        if not favorites:
            self.favorites_menu.add_separator()
            self.favorites_menu.add_command(label="(空)", state=tk.DISABLED)
        else:
            self.favorites_menu.add_separator()
            for path in favorites:
                display_name = os.path.basename(path) or path
                icon = "📁" if os.path.isdir(path) else "📄"
                self.favorites_menu.add_command(
                    label=f"{icon} {display_name}",
                    command=lambda p=path: self.open_favorite_item(p)
                )
    
    def open_favorite_item(self, path):
        """打开收��的项目"""
        if os.path.exists(path):
            if os.path.isfile(path):
                # 如是是文件，展开到文件所在目录并选中文件
                dir_path = os.path.dirname(path)
                self.expand_to_path(dir_path)
                
                # 选中并显示文件
                for item in self.tree.get_children(self.tree.focus()):
                    if self.tree.item(item)['values'][0] == path:
                        self.tree.selection_set(item)
                        self.tree.see(item)
                        self.on_tree_select(None)
                        break
            else:
                # 如果是文件夹，直接展开
                self.expand_to_path(path)
        else:
            messagebox.showwarning("警告", f"项目不存在：\n{path}")
            # 从收夹中移除不存的目
            favorites = self.get_favorites()
            favorites.remove(path)
            self.save_favorites(favorites)
            self.update_favorites_menu()
    
    def show_favorites_manager(self):
        """显示藏夹管理窗口"""
        dialog = tk.Toplevel(self.root)
        dialog.title("收藏夹整理")
        dialog.geometry("500x400")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 尝试��注册表加载位置
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.REG_KEYS['PATH'], 0,
                                winreg.KEY_READ)
            pos = json.loads(winreg.QueryValueEx(key, self.REG_KEYS['FAVORITES_POS'])[0])
            winreg.CloseKey(key)
            
            # 检查位置是否有效
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            dialog_width = 500
            dialog_height = 400
            
            # 如果位置会导致窗口超出屏幕范围，则使用默认中心位置
            if (pos['x'] < 0 or pos['x'] + dialog_width > screen_width or
                pos['y'] < 0 or pos['y'] + dialog_height > screen_height):
                raise ValueError("Position out of screen")
            
            # 设置位置
            dialog.geometry(f"+{pos['x']}+{pos['y']}")
        except (WindowsError, ValueError, json.JSONDecodeError):
            # 果没有保存位置或位置无效，居中显示
            dialog_width = 500
            dialog_height = 400
            x = (self.root.winfo_screenwidth() - dialog_width) // 2
            y = (self.root.winfo_screenheight() - dialog_height) // 2
            dialog.geometry(f"+{x}+{y}")
        
        # 创建列表框
        listbox = tk.Listbox(dialog, selectmode=tk.SINGLE)
        listbox.pack(fill='both', expand=True, padx=5, pady=5)
        
        # 获取收藏列表
        favorites = self.get_favorites()
        
        # 填充列表
        for path in favorites:
            display_name = os.path.basename(path) or path
            icon = "📁" if os.path.isdir(path) else "📄"
            listbox.insert(tk.END, f"{icon} {display_name} ({path})")
        
        # 创建按钮框架
        button_frame = tk.Frame(dialog)
        button_frame.pack(fill='x', padx=5, pady=5)
        
        # 左侧按钮框架
        left_buttons = tk.Frame(button_frame)
        left_buttons.pack(side='left')
        
        # 上移按钮
        tk.Button(left_buttons, text="上移",
                 command=lambda: self.move_favorite(listbox, -1)).pack(side='left')
        
        # 下移钮
        tk.Button(left_buttons, text="下移",
                 command=lambda: self.move_favorite(listbox, 1)).pack(side='left')
        
        # 删除按钮
        tk.Button(left_buttons, text="删除",
                 command=lambda: self.delete_favorite(listbox)).pack(side='left')
        
        # 部删除钮
        tk.Button(left_buttons, text="全部删除",
                 command=lambda: self.delete_all_favorites(listbox)).pack(side='left')
        
        # 检查失效项目按钮
        tk.Button(left_buttons, text="检查失效项目",
                 command=lambda: self.check_invalid_favorites(listbox)).pack(side='left')
        
        # 确定按钮 - 设置宽度为原来的2
        tk.Button(button_frame, text="确定", width=16,  # 设置宽度
                 command=lambda: self.save_favorites_order(listbox, dialog)).pack(side='right', padx=5)
        
        # 保存窗口位置
        def save_position():
            try:
                key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, self.REG_KEYS['PATH'], 0,
                                       winreg.KEY_WRITE)
                pos = {'x': dialog.winfo_x(), 'y': dialog.winfo_y()}
                winreg.SetValueEx(key, self.REG_KEYS['FAVORITES_POS'], 0, winreg.REG_SZ,
                                json.dumps(pos))
                winreg.CloseKey(key)
            except WindowsError as e:
                print(f"无法保窗口位置: {e}")
        
        # 在口关闭时保存位置
        dialog.bind("<Configure>", lambda e: save_position() if e.widget == dialog else None)
    
    def move_favorite(self, listbox, direction):
        """移动收藏项目"""
        selection = listbox.curselection()
        if not selection:
            return
        
        index = selection[0]
        if direction < 0 and index == 0:
            return
        if direction > 0 and index == listbox.size() - 1:
            return
        
        # 获取项目
        text = listbox.get(index)
        listbox.delete(index)
        new_index = index + direction
        listbox.insert(new_index, text)
        listbox.selection_set(new_index)
    
    def delete_favorite(self, listbox):
        """删除收藏项目"""
        selection = listbox.curselection()
        if not selection:
            return
        
        if messagebox.askyesno("确认", "确定要删除选中的收藏吗？"):
            listbox.delete(selection)
    
    def delete_all_favorites(self, listbox):
        """删除所有收藏"""
        if not listbox.size():
            return
        
        if messagebox.askyesno("确认", "确定要删除所有收藏吗？", icon='warning'):
            listbox.delete(0, tk.END)
            self.save_favorites([])
            self.update_favorites_menu()
    
    def check_invalid_favorites(self, listbox):
        """检查失效的收藏项目"""
        invalid_count = 0
        i = 0
        while i < listbox.size():
            text = listbox.get(i)
            path = text[text.rfind('(') + 1:-1]
            if not os.path.exists(path):
                listbox.delete(i)
                invalid_count += 1
            else:
                i += 1
        
        if invalid_count > 0:
            messagebox.showinfo("提示", f"已删除 {invalid_count} 个失效的收藏项目")
        else:
            messagebox.showinfo("提示", "没有发现失效的收藏项目")
    
    def save_favorites_order(self, listbox, dialog):
        """保存藏夹新顺序"""
        favorites = []
        for i in range(listbox.size()):
            text = listbox.get(i)
            path = text[text.rfind('(') + 1:-1]
            favorites.append(path)
        
        self.save_favorites(favorites)
        self.update_favorites_menu()
        dialog.destroy()
    
    def select_and_center_file(self, file_path):
        """选中文件并将其居中显示"""
        def try_center_file(retry_count=0):
            # 遍历所有可见的项目
            for item in self.tree.get_children(self.tree.focus()):
                if self.tree.item(item)['values'][0] == file_path:
                    # 选中文件
                    self.tree.selection_set(item)
                    self.tree.focus(item)
                    
                    # 先确保项目可见
                    self.tree.see(item)
                    
                    # 等待一小段时间确保UI已更新
                    self.root.update()
                    
                    # 获取项目的边界框
                    bbox = self.tree.bbox(item)
                    print(f"尝试次数: {retry_count + 1}")
                    print(f"边界框信息: {bbox}")
                    
                    if not bbox and retry_count < 5:  # 最多重试5次
                        print(f"无法获取边界框，将在200ms后重试")
                        self.root.after(200, lambda: try_center_file(retry_count + 1))
                        return
                    
                    if not bbox:
                        print("警告: 多次尝试后仍无法取界框信��")
                        return
                    
                    # 获取屏幕高度
                    screen_height = self.root.winfo_screenheight()
                    print(f"屏幕高度: {screen_height}")
                    
                    # 获取目录树在屏上的位置
                    tree_y = self.tree.winfo_rooty()
                    print(f"目录树Y坐标: {tree_y}")
                    
                    # 获取项目在目录树中的相对位置
                    item_y = bbox[1]  # bbox[1] 是项目的y坐标
                    print(f"目相对Y坐标: {item_y}")
                    
                    # 计算项目在屏幕上的绝对位置
                    absolute_item_y = tree_y + item_y
                    print(f"项目绝对Y坐标: {absolute_item_y}")
                    
                    # 计算到屏幕中心的距离
                    target_y = screen_height / 2
                    print(f"目标Y坐标: {target_y}")
                    print(f"需要调整的距离: {absolute_item_y - target_y}")
                    
                    # 将距离转换为滚动单位
                    tree_height = float(self.tree.winfo_height())
                    scroll_fraction = (absolute_item_y - target_y) / tree_height
                    print(f"滚动比例: {scroll_fraction}")
                    
                    # 获取当前滚动位置
                    current_pos = self.tree.yview()[0]
                    print(f"当前滚动位置: {current_pos}")
                    
                    # 计算新的滚动位置
                    new_pos = current_pos + scroll_fraction
                    new_pos = max(0.0, min(1.0, new_pos))
                    print(f"新的滚动位置: {new_pos}")
                    
                    # 应用滚动
                    self.tree.yview_moveto(new_pos)
                    
                    # 触发选择事件来显示图片
                    self.on_tree_select(None)
                    break
        
        # 开始尝试居中显示
        try_center_file()
    
    def handle_registry_error(self, operation, error):
        """统一处理注册表操作错误"""
        print(f"注册表{operation}错误: {error}")
        if isinstance(error, WindowsError):
            if error.winerror == 2:  # 找不到注册表键
                return None
        return False
    
    def registry_operation(self, operation, key, value=None):
        """统一处理注册表操作"""
        try:
            reg_key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, self.REG_KEYS['PATH'], 0,
                                       winreg.KEY_WRITE if value else winreg.KEY_READ)
            if value:
                winreg.SetValueEx(reg_key, key, 0, winreg.REG_SZ, value)
            else:
                value = winreg.QueryValueEx(reg_key, key)[0]
            winreg.CloseKey(reg_key)
            return value
        except Exception as e:
            return self.handle_registry_error(operation, e)
    
    def show_help(self):
        """显示帮助窗口"""
        help_text = """
本软件用于浏览较长的乐谱，它可将长乐谱切分为数个页面并显示，方便演奏者在不用翻页或尽量少翻页的情况下进行演奏。本软件也可用于浏览其他类型的长图，在超宽显示器上具有更好的效果。详细功能介绍如下：

1. 自动将超长图片切分为数个页面，并排显示。每个页面之间存在一定的重叠内容，重叠部分使用红线进行了标识。

2. 按下鼠标中键（滚轮）或点击菜单栏"遮罩"选项，可以为重叠部分增加绿色半透明遮罩，让重叠部分更加显眼，方便演奏者定位。

3. 按下小键盘上的+和-按键，可以放大或缩小图片。图片被放大或缩小后，切分页面数量会产生变化。

4. 按下Ctrl键不放并滚动鼠标滚轮，可增加或减少重叠部分的百分比，最小为5%，最大为30%。

5. 滚动鼠标滚轮，可以控制水平滚动条，用于展示更多的页面，用于页面较多，显示器一屏显示不完的情况。

6. 在任意文件或文件夹上点击鼠标右键，该文件或文件夹会被自动收藏到收藏夹。被收藏过的文件或文件夹会以加粗的形式进行显示。在菜单栏的"收藏夹"菜单中可以快捷访问这些收藏的文件或文件夹，也可以进行整理。最多可收藏50个项目。

7. 目录框架的宽度可以通过拖动目录框架与图片框架之间的分隔条来进行调节。

8. 软件具有记忆功能，可以记录每个浏览过的文件的大小、重复比例等信息；还可以记忆遮罩开关状态、最后一次访问的文件或文件夹、目录框架宽度等信息。记忆的信息存放在与软件同一个文件夹下的setup.ini文件中。如删除此文件，所有记忆的信息将丢失。

9. 在每个浏览过图片的文件夹中，会生成一个名为image_config.json的文件，该文件记录了被浏览过的图片的展示信息，如切分大小，遮罩大小等。没有被浏览过的图片不会在此文件中留下信息，浏览过但是又被删除了的图片，信息会从此文件中移除。如果删除此文件，所有记忆的信息将丢失。

10. Have Fun!

"""

        
        dialog = tk.Toplevel(self.root)
        dialog.title("帮助")
        dialog.geometry("550x650")
        dialog.resizable(False, True)  # 只允许垂直方向调整大小
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 创建主框架
        main_frame = tk.Frame(dialog)
        main_frame.pack(fill='both', expand=True)
        
        # 创建文本框和滚动条
        text_frame = tk.Frame(main_frame)
        text_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        scrollbar = tk.Scrollbar(text_frame)
        scrollbar.pack(side='right', fill='y')
        
        text = tk.Text(text_frame, wrap='word', yscrollcommand=scrollbar.set, 
                      font=('Microsoft YaHei', 10))  # 使用微软雅黑字体
        text.pack(side='left', fill='both', expand=True)
        
        scrollbar.config(command=text.yview)
        
        # 插入帮助文本
        text.insert('1.0', help_text)
        text.config(state='disabled')  # 设置为只读
        
        # 创建底部的确定按钮框架
        button_frame = tk.Frame(main_frame)
        button_frame.pack(fill='x', padx=10, pady=(0, 10))
        
        # 添加确定按钮
        ok_button = tk.Button(button_frame, text="确定", width=10, 
                             command=dialog.destroy)
        ok_button.pack(side='right')
        
        # 居中显示窗口
        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = (dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (dialog.winfo_screenheight() // 2) - (height // 2)
        dialog.geometry(f'+{x}+{y}')
    
    def sort_files(self, sort_method):
        """根据指定方法对文件进行排序"""
        # 获取当前选中的节点
        selected = self.tree.selection()
        if not selected:
            return
        
        # 获取当前目录节点
        current_node = selected[0]
        current_path = self.tree.item(current_node)['values'][0]
        
        # 如果选中的是文件，获取其父目录
        if os.path.isfile(current_path):
            current_node = self.tree.parent(current_node)
            current_path = self.tree.item(current_node)['values'][0]
        
        # 保存排序方法到配置文件
        config_path = os.path.join(current_path, self.config_filename)
        try:
            # 读取现有配置
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    configs = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                configs = {}
            
            # 更新排序方法
            configs['sort_method'] = sort_method
            
            # 保存配置
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(configs, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"无法保存排序方法: {e}")
        
        # 清空当前目录下的所有项目
        for item in self.tree.get_children(current_node):
            self.tree.delete(item)
        
        # 重新填充目录
        self.populate_node(current_node)
    
    def refresh_directory(self):
        """刷新当前目录"""
        if not self.last_visited_directory:
            return
        
        # 获取当前选中的项目
        selected = self.tree.selection()
        if selected:
            current_path = self.tree.item(selected[0])['values'][0]
        else:
            current_path = None
        
        # 获取当前焦点项目（通常是当前目录）
        current_node = self.tree.focus()
        if not current_node:
            return
        
        # 清空当前目录下的所有项目
        for item in self.tree.get_children(current_node):
            self.tree.delete(item)
        
        # 重新填充目录
        self.populate_node(current_node)
        
        # 如果之前有选中的项目，尝试重新选中
        if current_path:
            for item in self.tree.get_children(current_node):
                if self.tree.item(item)['values'][0] == current_path:
                    self.tree.selection_set(item)
                    break
    
    def get_sort_method(self, directory):
        """获取目录的排序方法"""
        config_path = os.path.join(directory, self.config_filename)
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                configs = json.load(f)
                return configs.get('sort_method', 'name_asc')  # 默认按名称升序
        except (FileNotFoundError, json.JSONDecodeError):
            return 'name_asc'  # 默认按名称升序

if __name__ == "__main__":
    root = tk.Tk()
    app = ImageViewer(root)
    root.mainloop()
