import os
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import json
import winreg
import threading
import time
import queue
import ctypes

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
            'FAVORITES_POS': 'FavoritesManagerPos',
            'SEARCH_RESULTS_SIZE': 'SearchResultsSize',
            'SEARCH_RESULTS_POSITION': 'SearchResultsPosition'
        }
        
        # 添加遮罩控制变量，并从配置文件加载上次的状态
        self.show_mask = tk.BooleanVar()
        try:
            config = self.load_config()
            self.show_mask.set(bool(int(config.get(self.CONFIG_KEYS['MASK_STATE'], '0'))))
        except:
            self.show_mask.set(False)

        # 搜索功能状态。文件扫描放在线程中执行，避免搜索大量子文件夹时界面卡死。
        self.search_query = tk.StringVar()
        self.search_subfolders = tk.BooleanVar(value=False)
        self.search_status = tk.StringVar(value="尚未开始搜索")
        self.search_stop_event = threading.Event()
        self.search_thread = None
        self.search_result_queue = None
        self.search_results_window = None
        self.search_results_listbox = None
        self.search_result_paths = []
        self.search_poll_job = None
        self.search_size_save_job = None
        self.search_generation = 0
        self.search_result_count = 0
        
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
        self.scrollbar = tk.Scrollbar(
            self.right_frame,
            orient='horizontal',
            command=self.on_horizontal_scroll
        )
        self.scrollbar.pack(side='bottom', fill='x')
        self.canvas.configure(xscrollcommand=self.scrollbar.set)
        
        # 当前图片和缩放比例
        self.current_image = None
        self.scale = 1.0
        self.current_directory = None  # 初始化当前目录

        # 分页按需渲染状态：Pillow 在线程中缩放，Tk 图片仅在主线程中创建。
        self.render_generation = 0
        self.lazy_render_context = None
        self.lazy_render_task_queue = queue.PriorityQueue()
        self.lazy_render_result_queue = queue.Queue()
        self.lazy_render_stop_event = threading.Event()
        self.lazy_render_thread = None
        self.lazy_render_poll_job = None
        self.lazy_view_request_job = None
        self.deferred_render_job = None
        self.zoom_render_job = None
        self.lazy_task_sequence = 0
        self.lazy_page_items = {}
        self.lazy_page_placeholders = {}
        self.lazy_page_images = {}
        self.lazy_page_request_ids = {}
        self.lazy_page_request_priorities = {}
        self.lazy_needed_pages = set()
        self.lazy_failed_pages = set()
        self.lazy_prefetch_count = 2
        self.photo_images = []
        self.start_lazy_render_worker()
        
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
        # Tk 原生菜单不能直接放置文本框和普通按钮，因此使用顶部自定义菜单栏，
        # 既保留原有菜单，也让搜索控件真正位于同一栏中。
        self.menu_bar = tk.Frame(self.root, relief=tk.RAISED, borderwidth=1)
        self.menu_bar.pack(side='top', fill='x')
        
        # 创建收藏夹菜单
        favorites_button = tk.Menubutton(
            self.menu_bar, text="收藏夹", relief=tk.FLAT, padx=8, pady=3
        )
        favorites_button.pack(side='left')
        self.favorites_menu = tk.Menu(favorites_button, tearoff=0)
        favorites_button.configure(menu=self.favorites_menu)
        self.favorites_menu.add_command(label="整理收藏夹", command=self.show_favorites_manager)
        
        # 创建排序菜单
        sort_button = tk.Menubutton(
            self.menu_bar, text="排序", relief=tk.FLAT, padx=8, pady=3
        )
        sort_button.pack(side='left')
        sort_menu = tk.Menu(sort_button, tearoff=0)
        sort_button.configure(menu=sort_menu)
        sort_menu.add_command(label="时间倒序", command=lambda: self.sort_files("time_desc"))
        sort_menu.add_command(label="时间顺序", command=lambda: self.sort_files("time_asc"))
        sort_menu.add_command(label="名称倒序", command=lambda: self.sort_files("name_desc"))
        sort_menu.add_command(label="名称顺序", command=lambda: self.sort_files("name_asc"))
        
        # 添加遮罩选项
        tk.Checkbutton(
            self.menu_bar,
            text="遮罩",
            variable=self.show_mask,
            command=self.refresh_image,
            relief=tk.FLAT,
            padx=8
        ).pack(side='left')
        
        # 添加帮助菜单
        tk.Button(
            self.menu_bar,
            text="帮助",
            command=self.show_help,
            relief=tk.FLAT,
            padx=8,
            pady=3
        ).pack(side='left')

        ttk.Separator(self.menu_bar, orient=tk.VERTICAL).pack(
            side='left', fill='y', padx=6, pady=3
        )

        # 搜索控件
        tk.Label(self.menu_bar, text="搜索：").pack(side='left')
        self.search_entry = tk.Entry(
            self.menu_bar, textvariable=self.search_query, width=32
        )
        self.search_entry.pack(side='left', padx=(0, 5), pady=3)
        self.search_entry.bind('<Return>', lambda event: self.start_search())

        self.search_button = tk.Button(
            self.menu_bar, text="搜索", command=self.start_search, padx=10
        )
        self.search_button.pack(side='left', padx=(0, 4), pady=2)

        self.stop_search_button = tk.Button(
            self.menu_bar,
            text="停止搜索",
            command=self.stop_search,
            state=tk.DISABLED,
            padx=10
        )
        self.stop_search_button.pack(side='left', padx=(0, 6), pady=2)

        tk.Checkbutton(
            self.menu_bar,
            text="搜索子文件夹",
            variable=self.search_subfolders,
            relief=tk.FLAT
        ).pack(side='left', padx=(0, 6))
        
        # 更新收藏夹菜单
        self.update_favorites_menu()

    def get_current_search_directory(self):
        """返回当前打开的文件夹，文件节点按其所在文件夹处理。"""
        if self.current_directory and os.path.isdir(self.current_directory):
            return os.path.abspath(self.current_directory)

        selected = self.tree.selection()
        if selected:
            values = self.tree.item(selected[0]).get('values', ())
            if values:
                selected_path = os.path.abspath(values[0])
                if os.path.isdir(selected_path):
                    return selected_path
                if os.path.isfile(selected_path):
                    return os.path.dirname(selected_path)

        if hasattr(self, 'current_file_path') and os.path.isfile(self.current_file_path):
            return os.path.dirname(os.path.abspath(self.current_file_path))

        if self.last_visited_directory and os.path.isdir(self.last_visited_directory):
            return os.path.abspath(self.last_visited_directory)

        return None

    def start_search(self):
        """从当前文件夹开始异步搜索图片文件。"""
        root_directory = self.get_current_search_directory()
        if not root_directory:
            messagebox.showwarning("无法搜索", "请先在目录树中打开一个文件夹。")
            return

        # 终止仍在收尾的旧搜索，并使旧轮询回调失效。
        self.search_stop_event.set()
        if self.search_poll_job is not None:
            try:
                self.root.after_cancel(self.search_poll_job)
            except tk.TclError:
                pass
            self.search_poll_job = None

        self.search_generation += 1
        generation = self.search_generation
        self.search_stop_event = threading.Event()
        self.search_result_queue = queue.Queue()
        self.search_result_count = 0
        self.search_result_paths = []

        query_text = self.search_query.get().strip()
        include_subfolders = self.search_subfolders.get()
        self.show_search_results_window(root_directory, query_text)
        self.search_status.set("正在搜索……已找到 0 个文件")
        self.search_button.configure(state=tk.DISABLED)
        self.stop_search_button.configure(state=tk.NORMAL)

        self.search_thread = threading.Thread(
            target=self.search_files_worker,
            args=(
                root_directory,
                query_text.casefold(),
                include_subfolders,
                self.search_stop_event,
                self.search_result_queue
            ),
            daemon=True
        )
        self.search_thread.start()
        self.poll_search_results(generation, self.search_result_queue)

    def search_files_worker(self, root_directory, query, include_subfolders,
                            stop_event, result_queue):
        """后台扫描文件；所有 Tk 界面更新均交回主线程。"""
        result_count = 0
        error_count = 0

        def add_result(file_path):
            nonlocal result_count
            file_path = os.path.abspath(file_path)
            relative_path = os.path.relpath(file_path, root_directory)
            if query and query not in relative_path.casefold():
                return
            # 当前文件夹内只显示文件名；子文件夹内显示以当前文件夹为根的相对路径。
            if os.path.dirname(relative_path) in ('', '.'):
                display_path = os.path.basename(relative_path)
            else:
                display_path = relative_path
            result_queue.put(('result', display_path, file_path))
            result_count += 1

        def record_walk_error(error):
            nonlocal error_count
            error_count += 1

        try:
            if include_subfolders:
                for folder, subfolders, filenames in os.walk(
                        root_directory, topdown=True, onerror=record_walk_error,
                        followlinks=False):
                    if stop_event.is_set():
                        subfolders[:] = []
                        break

                    for filename in filenames:
                        if stop_event.is_set():
                            break
                        if filename.lower().endswith(self.IMAGE_EXTENSIONS):
                            add_result(os.path.join(folder, filename))
            else:
                try:
                    with os.scandir(root_directory) as entries:
                        for entry in entries:
                            if stop_event.is_set():
                                break
                            try:
                                if (entry.is_file() and
                                        entry.name.lower().endswith(self.IMAGE_EXTENSIONS)):
                                    add_result(entry.path)
                            except (OSError, PermissionError):
                                error_count += 1
                except (OSError, PermissionError):
                    error_count += 1
        except Exception:
            # 单个不可访问路径不应让整个程序退出，完成信息会提示跳过数量。
            error_count += 1
        finally:
            result_queue.put(
                ('done', result_count, stop_event.is_set(), error_count)
            )

    def get_saved_search_window_size(self):
        """读取并校验搜索结果窗口上次保存的宽高。"""
        default_width = 950
        default_height = 520
        try:
            config = self.load_config()
            saved_size = config.get(
                self.CONFIG_KEYS['SEARCH_RESULTS_SIZE'],
                f"{default_width}x{default_height}"
            )
            width_text, height_text = saved_size.lower().split('x', 1)
            width = int(width_text)
            height = int(height_text)

            # 避免损坏的配置或显示器变化导致窗口不可用。
            width = max(600, min(width, self.root.winfo_screenwidth()))
            height = max(300, min(height, self.root.winfo_screenheight()))
            return width, height
        except (ValueError, TypeError):
            return default_width, default_height

    def get_desktop_bounds(self):
        """返回当前虚拟桌面的左上角坐标及总宽高。"""
        if os.name == 'nt':
            try:
                # Windows 虚拟桌面包含所有当前启用的显示器，也支持负坐标副屏。
                user32 = ctypes.windll.user32
                left = user32.GetSystemMetrics(76)    # SM_XVIRTUALSCREEN
                top = user32.GetSystemMetrics(77)     # SM_YVIRTUALSCREEN
                width = user32.GetSystemMetrics(78)   # SM_CXVIRTUALSCREEN
                height = user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
                if width > 0 and height > 0:
                    return left, top, width, height
            except (AttributeError, OSError):
                pass

        return (0, 0, self.root.winfo_screenwidth(),
                self.root.winfo_screenheight())

    def get_default_search_window_position(self, width, height):
        """默认在当前主屏幕中央显示搜索结果窗口。"""
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        return x, y

    def get_saved_search_window_position(self, width, height):
        """读取保存位置；若窗口会超出当前桌面，则返回默认位置。"""
        default_position = self.get_default_search_window_position(width, height)
        try:
            config = self.load_config()
            saved_position = config.get(
                self.CONFIG_KEYS['SEARCH_RESULTS_POSITION'], ''
            )
            x_text, y_text = saved_position.split(',', 1)
            x = int(x_text)
            y = int(y_text)

            desktop_x, desktop_y, desktop_width, desktop_height = (
                self.get_desktop_bounds()
            )
            desktop_right = desktop_x + desktop_width
            desktop_bottom = desktop_y + desktop_height

            # 必须保证整个窗口都位于当前虚拟桌面内。
            if (x < desktop_x or y < desktop_y or
                    x + width > desktop_right or
                    y + height > desktop_bottom):
                return default_position
            return x, y
        except (ValueError, TypeError):
            return default_position

    def schedule_search_window_geometry_save(self, event=None):
        """移动或缩放窗口时延迟保存，避免操作过程中频繁写入配置文件。"""
        if (event is not None and
                event.widget is not self.search_results_window):
            return

        if self.search_size_save_job is not None:
            try:
                self.root.after_cancel(self.search_size_save_job)
            except tk.TclError:
                pass

        self.search_size_save_job = self.root.after(
            500, self.save_search_window_geometry
        )

    def save_search_window_geometry(self):
        """把搜索结果窗口当前大小和位置保存到 setup.ini。"""
        self.search_size_save_job = None
        if (self.search_results_window is None or
                not self.search_results_window.winfo_exists()):
            return

        # 最小化或最大化时的坐标不是用户可复用的普通窗口位置。
        if self.search_results_window.state() != 'normal':
            return

        width = self.search_results_window.winfo_width()
        height = self.search_results_window.winfo_height()
        x = self.search_results_window.winfo_x()
        y = self.search_results_window.winfo_y()
        if width >= 600 and height >= 300:
            self.save_config(
                self.CONFIG_KEYS['SEARCH_RESULTS_SIZE'],
                f"{width}x{height}"
            )
            self.save_config(
                self.CONFIG_KEYS['SEARCH_RESULTS_POSITION'],
                f"{x},{y}"
            )

    def show_search_results_window(self, root_directory, query_text):
        """创建或重用可移动、可关闭且非置顶的搜索结果窗口。"""
        window_exists = (
            self.search_results_window is not None and
            self.search_results_window.winfo_exists()
        )

        if not window_exists:
            self.search_results_window = tk.Toplevel(self.root)
            self.search_results_window.title("搜索结果")
            saved_width, saved_height = self.get_saved_search_window_size()
            saved_x, saved_y = self.get_saved_search_window_position(
                saved_width, saved_height
            )
            self.search_results_window.geometry(
                f"{saved_width}x{saved_height}{saved_x:+d}{saved_y:+d}"
            )
            self.search_results_window.minsize(600, 300)
            self.search_results_window.protocol(
                "WM_DELETE_WINDOW", self.close_search_results_window
            )
            self.search_results_window.bind(
                '<Configure>', self.schedule_search_window_geometry_save
            )

            self.search_root_label = tk.Label(
                self.search_results_window,
                anchor='w',
                justify='left',
                padx=8,
                pady=7
            )
            self.search_root_label.pack(fill='x')

            result_frame = tk.Frame(self.search_results_window)
            result_frame.pack(fill='both', expand=True, padx=8)

            vertical_scrollbar = tk.Scrollbar(result_frame, orient='vertical')
            vertical_scrollbar.pack(side='right', fill='y')
            horizontal_scrollbar = tk.Scrollbar(result_frame, orient='horizontal')
            horizontal_scrollbar.pack(side='bottom', fill='x')

            self.search_results_listbox = tk.Listbox(
                result_frame,
                selectmode=tk.SINGLE,
                yscrollcommand=vertical_scrollbar.set,
                xscrollcommand=horizontal_scrollbar.set
            )
            self.search_results_listbox.pack(fill='both', expand=True)
            vertical_scrollbar.configure(command=self.search_results_listbox.yview)
            horizontal_scrollbar.configure(command=self.search_results_listbox.xview)
            self.search_results_listbox.bind(
                '<<ListboxSelect>>', self.open_selected_search_result
            )

            tk.Label(
                self.search_results_window,
                textvariable=self.search_status,
                anchor='w',
                padx=8,
                pady=7
            ).pack(fill='x')
        else:
            self.search_results_window.deiconify()
            self.search_results_window.lift()

        keyword_display = query_text if query_text else "（空，列出全部图片）"
        root_name = os.path.basename(os.path.normpath(root_directory))
        root_display = root_name if root_name else "当前打开文件夹"
        self.search_root_label.configure(
            text=(f"根目录：{root_display}（以下路径均相对此文件夹）\n"
                  f"关键词：{keyword_display}")
        )
        self.search_results_listbox.delete(0, tk.END)
        self.search_result_paths = []

    def poll_search_results(self, generation, result_queue):
        """分批把后台搜索结果加入列表，保持界面响应。"""
        if generation != self.search_generation:
            return

        if (self.search_results_window is None or
                not self.search_results_window.winfo_exists()):
            self.search_stop_event.set()
            return

        done_info = None
        processed = 0
        while processed < 300:
            try:
                item = result_queue.get_nowait()
            except queue.Empty:
                break

            processed += 1
            if item[0] == 'result':
                # 界面显示相对路径，真实绝对路径只保存在内部列表中用于加载图片。
                self.search_results_listbox.insert(tk.END, item[1])
                self.search_result_paths.append(item[2])
                self.search_result_count += 1
            elif item[0] == 'done':
                done_info = item
                break

        if done_info is not None:
            _, result_count, was_stopped, error_count = done_info
            if was_stopped:
                status_text = f"搜索已停止，共找到 {result_count} 个文件"
            else:
                status_text = f"搜索完成，共找到 {result_count} 个文件"
            if error_count:
                status_text += f"；跳过 {error_count} 个无法访问的项目"
            self.search_status.set(status_text)
            self.search_button.configure(state=tk.NORMAL)
            self.stop_search_button.configure(state=tk.DISABLED)
            self.search_thread = None
            self.search_poll_job = None
            return

        self.search_status.set(
            f"正在搜索……已找到 {self.search_result_count} 个文件"
        )
        self.search_poll_job = self.root.after(
            50, lambda: self.poll_search_results(generation, result_queue)
        )

    def stop_search(self):
        """请求后台线程停止当前搜索。"""
        if self.search_thread is not None and self.search_thread.is_alive():
            self.search_stop_event.set()
            self.search_status.set("正在停止搜索……")
            self.stop_search_button.configure(state=tk.DISABLED)

    def close_search_results_window(self):
        """关闭结果窗口，同时终止与该窗口对应的搜索。"""
        self.search_stop_event.set()
        self.search_generation += 1
        if self.search_poll_job is not None:
            try:
                self.root.after_cancel(self.search_poll_job)
            except tk.TclError:
                pass
            self.search_poll_job = None

        if self.search_size_save_job is not None:
            try:
                self.root.after_cancel(self.search_size_save_job)
            except tk.TclError:
                pass
            self.search_size_save_job = None

        # 销毁窗口前立即保存，确保下次打开时恢复最后的大小和位置。
        self.save_search_window_geometry()

        if (self.search_results_window is not None and
                self.search_results_window.winfo_exists()):
            self.search_results_window.destroy()
        self.search_results_window = None
        self.search_results_listbox = None
        self.search_result_paths = []
        self.search_button.configure(state=tk.NORMAL)
        self.stop_search_button.configure(state=tk.DISABLED)

    def open_selected_search_result(self, event=None):
        """单击搜索结果后，在主窗口中显示图片并保持结果窗口在前。"""
        if self.search_results_listbox is None:
            return
        selection = self.search_results_listbox.curselection()
        if not selection:
            return

        selected_index = selection[0]
        if selected_index >= len(self.search_result_paths):
            return
        file_path = self.search_result_paths[selected_index]
        if not os.path.isfile(file_path):
            messagebox.showwarning(
                "文件不存在", f"该文件可能已被移动或删除：\n{file_path}",
                parent=self.search_results_window
            )
            return

        try:
            self.display_image(file_path)
            self.current_directory = os.path.dirname(file_path)
            self.last_visited_directory = self.current_directory
        except Exception as error:
            messagebox.showerror(
                "无法打开图片", f"无法加载图片：\n{file_path}\n\n{error}",
                parent=self.search_results_window
            )
    
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
            self.current_directory = self.last_visited_directory
        else:
            # 如果是目录，切换展开/收拢状态
            self.last_visited_directory = file_path
            self.current_directory = file_path
            is_open = self.tree.item(selected_item, 'open')
            self.tree.item(selected_item, open=not is_open)
            
            if not is_open:  # 如果是展开操作
                children = self.tree.get_children(selected_item)
                if children and self.tree.item(children[0])['text'] == '':
                    self.tree.delete(children[0])
                    self.populate_node(selected_item)
    
    def start_lazy_render_worker(self):
        """启动唯一的后台 Pillow 渲染线程。"""
        if self.lazy_render_thread is not None and self.lazy_render_thread.is_alive():
            return
        self.lazy_render_stop_event.clear()
        self.lazy_render_thread = threading.Thread(
            target=self.lazy_render_worker,
            daemon=True
        )
        self.lazy_render_thread.start()

    def lazy_render_worker(self):
        """后台逐页缩放；不能在此线程中创建任何 Tk 对象。"""
        while not self.lazy_render_stop_event.is_set():
            try:
                task = self.lazy_render_task_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            (_, _, _, _, generation, page_index,
             request_id, context) = task
            if generation != self.render_generation:
                continue

            page_image = None
            error = None
            try:
                page_image = self.render_lazy_page(context, page_index)
            except Exception as exc:
                error = str(exc)

            if generation == self.render_generation:
                self.lazy_render_result_queue.put(
                    (generation, page_index, request_id, page_image, error)
                )

    def render_lazy_page(self, context, page_index):
        """从原图对应区域直接生成一页，避免创建整张放大后的长图。"""
        source_image = context['source_image']
        scaled_width = context['scaled_width']

        if not context['split']:
            return source_image.resize(
                (scaled_width, context['scaled_height']),
                Image.Resampling.LANCZOS
            )

        start_y = page_index * context['effective_height']
        page_height = min(
            context['canvas_height'],
            context['scaled_height'] - start_y
        )

        # Pillow 的 box 参数可直接按整图坐标采样该页，效果与整图缩放后裁切一致。
        source_top = (
            start_y * source_image.height / context['scaled_height']
        )
        source_bottom = (
            (start_y + page_height) * source_image.height /
            context['scaled_height']
        )
        return source_image.resize(
            (scaled_width, page_height),
            Image.Resampling.LANCZOS,
            box=(0, source_top, source_image.width, source_bottom)
        )

    def begin_image_render(self):
        """使旧渲染任务失效并释放旧页面缓存。"""
        self.render_generation += 1
        generation = self.render_generation
        self.lazy_render_context = None

        for job_name in ('lazy_render_poll_job', 'lazy_view_request_job'):
            job = getattr(self, job_name)
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
                setattr(self, job_name, None)

        # 移除尚未开始的旧任务；正在处理的单页会在完成后因代次不符而被丢弃。
        for task_queue in (self.lazy_render_task_queue,
                           self.lazy_render_result_queue):
            while True:
                try:
                    task_queue.get_nowait()
                except queue.Empty:
                    break

        self.lazy_page_items = {}
        self.lazy_page_placeholders = {}
        self.lazy_page_images = {}
        self.lazy_page_request_ids = {}
        self.lazy_page_request_priorities = {}
        self.lazy_needed_pages = set()
        self.lazy_failed_pages = set()
        self.photo_images = []
        self.canvas.image = None
        return generation

    def cancel_pending_zoom_render(self):
        if self.zoom_render_job is not None:
            try:
                self.root.after_cancel(self.zoom_render_job)
            except tk.TclError:
                pass
            self.zoom_render_job = None

    def display_image(self, file_path):
        self.cancel_pending_zoom_render()
        self.current_image = Image.open(file_path)
        self.current_file_path = file_path  # 存当前文件路径
        self.current_directory = os.path.dirname(os.path.abspath(file_path))
        self.load_image_config(file_path)  # 加载设置
        self.reset_view_on_next_render = True
        self.show_image()

    def run_deferred_image_render(self):
        self.deferred_render_job = None
        self.show_image()

    def show_image(self):
        if not self.current_image:
            return

        canvas_height = self.canvas.winfo_height()
        if canvas_height < 20:
            # 程序刚启动时画布可能暂时只有 1 像素，等布局完成后再分页。
            if self.deferred_render_job is None:
                self.deferred_render_job = self.root.after(
                    100, self.run_deferred_image_render
                )
            return

        if self.deferred_render_job is not None:
            try:
                self.root.after_cancel(self.deferred_render_job)
            except tk.TclError:
                pass
            self.deferred_render_job = None

        old_xview = self.canvas.xview()[0]
        if getattr(self, 'reset_view_on_next_render', False):
            old_xview = 0.0
            self.reset_view_on_next_render = False

        source_width, source_height = self.current_image.size
        scaled_width = max(1, int(source_width * self.scale))
        scaled_height = max(1, int(source_height * self.scale))
        generation = self.begin_image_render()
        self.canvas.delete("all")

        if scaled_height > canvas_height:
            self.split_image(
                self.current_image,
                scaled_width,
                scaled_height,
                canvas_height,
                generation
            )
        else:
            self.setup_lazy_single_image(
                self.current_image,
                scaled_width,
                scaled_height,
                canvas_height,
                generation
            )

        self.canvas.xview_moveto(old_xview)
        self.schedule_visible_page_request(0)

    def setup_lazy_single_image(self, source_image, width, height,
                                canvas_height, generation):
        """单页图片也交给后台缩放，避免大宽图阻塞主线程。"""
        total_width = max(width, 1)
        self.canvas.config(
            scrollregion=(0, 0, total_width, max(canvas_height, height))
        )
        self.lazy_render_context = {
            'generation': generation,
            'source_image': source_image,
            'scale': self.scale,
            'scaled_width': width,
            'scaled_height': height,
            'canvas_height': canvas_height,
            'effective_height': height,
            'num_pages': 1,
            'page_width': total_width,
            'total_width': total_width,
            'split': False
        }
        self.lazy_page_items[0] = self.canvas.create_image(
            0, 0, anchor='nw'
        )
        self.lazy_page_placeholders[0] = self.canvas.create_text(
            min(width, max(100, self.canvas.winfo_width())) / 2,
            min(height, canvas_height) / 2,
            text="正在生成图片……",
            fill='#7f8c8d',
            font=('Arial', 11)
        )

    def split_image(self, source_image, width, height,
                    canvas_height, generation):
        """建立分页骨架；实际页面由可见范围驱动按需生成。"""
        overlap = int(canvas_height * self.overlap_ratio)
        effective_height = max(1, canvas_height - overlap)
        num_pages = (height + effective_height - 1) // effective_height
        page_width = width + 20
        total_width = page_width * num_pages
        self.canvas.config(scrollregion=(0, 0, total_width, canvas_height))

        self.lazy_render_context = {
            'generation': generation,
            'source_image': source_image,
            'scale': self.scale,
            'scaled_width': width,
            'scaled_height': height,
            'canvas_height': canvas_height,
            'effective_height': effective_height,
            'num_pages': num_pages,
            'page_width': page_width,
            'total_width': total_width,
            'split': True
        }

        mask_photo = None
        if self.show_mask.get() and overlap > 0:
            mask_color = (144, 238, 144, 25)
            mask_image = Image.new('RGBA', (width, overlap), mask_color)
            mask_photo = ImageTk.PhotoImage(mask_image)
            self.photo_images.append(mask_photo)

        for i in range(num_pages):
            x = i * page_width + 10
            border_x = x - 5

            self.canvas.create_rectangle(
                border_x, 5,
                border_x + width + 10, canvas_height - 5,
                outline='#4a90e2', width=2, dash=None
            )
            self.canvas.create_line(
                border_x + 1, 6, border_x + width + 9, 6,
                fill='#2c3e50', width=1
            )
            self.canvas.create_line(
                border_x + 1, 6, border_x + 1, canvas_height - 6,
                fill='#2c3e50', width=1
            )
            self.canvas.create_line(
                border_x + 1, canvas_height - 6,
                border_x + width + 9, canvas_height - 6,
                fill='#2c3e50', width=1
            )

            self.lazy_page_items[i] = self.canvas.create_image(
                x, 10, anchor='nw'
            )

            if mask_photo is not None:
                if i == 0:
                    self.canvas.create_image(
                        x, canvas_height - overlap + 10,
                        anchor='nw', image=mask_photo
                    )
                else:
                    self.canvas.create_image(
                        x, 10, anchor='nw', image=mask_photo
                    )
                    if i < num_pages - 1:
                        self.canvas.create_image(
                            x, canvas_height - overlap + 10,
                            anchor='nw', image=mask_photo
                        )

            if i == 0:
                self.canvas.create_line(
                    x, canvas_height - overlap + 10,
                    x + width, canvas_height - overlap + 10,
                    fill='red', width=1
                )
            else:
                self.canvas.create_line(
                    x, overlap + 10, x + width, overlap + 10,
                    fill='red', width=1
                )
                if i < num_pages - 1:
                    self.canvas.create_line(
                        x, canvas_height - overlap + 10,
                        x + width, canvas_height - overlap + 10,
                        fill='red', width=1
                    )

            self.canvas.create_text(
                border_x + width / 2 + 5,
                canvas_height - 20,
                text=(f"第 {i + 1}/{num_pages} 页 "
                      f"(重叠: {int(self.overlap_ratio * 100)}%)"),
                fill='#4a90e2',
                font=('Arial', 10)
            )
            self.lazy_page_placeholders[i] = self.canvas.create_text(
                x + min(width, max(100, self.canvas.winfo_width())) / 2,
                canvas_height / 2,
                text=f"正在生成第 {i + 1} 页……",
                fill='#7f8c8d',
                font=('Arial', 11)
            )

    def on_horizontal_scroll(self, *args):
        self.canvas.xview(*args)
        self.schedule_visible_page_request()

    def schedule_visible_page_request(self, delay=30):
        if self.lazy_render_context is None:
            return
        if self.lazy_view_request_job is not None:
            try:
                self.root.after_cancel(self.lazy_view_request_job)
            except tk.TclError:
                pass
        self.lazy_view_request_job = self.root.after(
            delay, self.request_visible_pages
        )

    def request_visible_pages(self):
        """优先请求当前可见页，并预取前后相邻页面。"""
        self.lazy_view_request_job = None
        context = self.lazy_render_context
        if context is None or context['generation'] != self.render_generation:
            return

        page_width = max(1, context['page_width'])
        total_width = max(1, context['total_width'])
        canvas_width = max(1, self.canvas.winfo_width())
        view_left = self.canvas.xview()[0] * total_width
        view_right = min(total_width, view_left + canvas_width)
        first_visible = max(0, int(view_left // page_width))
        last_visible = min(
            context['num_pages'] - 1,
            int(max(view_left, view_right - 1) // page_width)
        )

        visible_pages = set(range(first_visible, last_visible + 1))
        first_needed = max(0, first_visible - self.lazy_prefetch_count)
        last_needed = min(
            context['num_pages'] - 1,
            last_visible + self.lazy_prefetch_count
        )
        needed_pages = set(range(first_needed, last_needed + 1))
        self.lazy_needed_pages = needed_pages

        # 视野已经离开的未完成请求作废；以后滚回时会按新的优先级重新请求。
        for page_index in list(self.lazy_page_request_ids):
            if (page_index not in needed_pages and
                    page_index not in self.lazy_page_images):
                self.lazy_page_request_ids.pop(page_index, None)
                self.lazy_page_request_priorities.pop(page_index, None)
        self.lazy_failed_pages.intersection_update(needed_pages)

        # 只保留可见页和邻页，远处页面释放后可在再次接近时重新生成。
        for page_index in list(self.lazy_page_images):
            if page_index not in needed_pages:
                try:
                    self.canvas.itemconfigure(
                        self.lazy_page_items[page_index], image=''
                    )
                    self.canvas.itemconfigure(
                        self.lazy_page_placeholders[page_index],
                        state='normal', text=f"正在生成第 {page_index + 1} 页……"
                    )
                except tk.TclError:
                    pass
                self.lazy_page_images.pop(page_index, None)
                self.lazy_page_request_ids.pop(page_index, None)
                self.lazy_page_request_priorities.pop(page_index, None)
                self.lazy_failed_pages.discard(page_index)

        center_page = (first_visible + last_visible) / 2
        ordered_pages = sorted(
            needed_pages,
            key=lambda index: (
                0 if index in visible_pages else 1,
                abs(index - center_page)
            )
        )

        for page_index in ordered_pages:
            if (page_index in self.lazy_page_images or
                    page_index in self.lazy_failed_pages):
                continue
            urgency = 0 if page_index in visible_pages else 1
            old_priority = self.lazy_page_request_priorities.get(page_index)
            if old_priority is not None and old_priority <= urgency:
                continue

            self.lazy_task_sequence += 1
            request_id = self.lazy_task_sequence
            self.lazy_page_request_ids[page_index] = request_id
            self.lazy_page_request_priorities[page_index] = urgency
            try:
                self.canvas.itemconfigure(
                    self.lazy_page_placeholders[page_index],
                    state='normal', text=f"正在生成第 {page_index + 1} 页……"
                )
            except tk.TclError:
                pass
            self.lazy_render_task_queue.put(
                (
                    -self.render_generation,
                    urgency,
                    abs(page_index - center_page),
                    self.lazy_task_sequence,
                    self.render_generation,
                    page_index,
                    request_id,
                    context
                )
            )

        self.ensure_lazy_result_polling()

    def ensure_lazy_result_polling(self):
        if self.lazy_render_poll_job is None:
            self.lazy_render_poll_job = self.root.after(
                15, self.poll_lazy_render_results
            )

    def poll_lazy_render_results(self):
        """每次只把一页转换为 Tk 图片，避免集中创建导致界面停顿。"""
        self.lazy_render_poll_job = None
        try:
            result = self.lazy_render_result_queue.get_nowait()
        except queue.Empty:
            result = None

        if result is not None:
            generation, page_index, request_id, page_image, error = result
            current_request = self.lazy_page_request_ids.get(page_index)
            result_is_current = (
                generation == self.render_generation and
                request_id == current_request and
                page_index in self.lazy_needed_pages and
                page_index in self.lazy_page_items
            )

            if result_is_current:
                if error is not None or page_image is None:
                    self.lazy_failed_pages.add(page_index)
                    self.canvas.itemconfigure(
                        self.lazy_page_placeholders[page_index],
                        text="该页生成失败", state='normal'
                    )
                else:
                    try:
                        photo = ImageTk.PhotoImage(page_image)
                        self.lazy_page_images[page_index] = photo
                        self.canvas.itemconfigure(
                            self.lazy_page_items[page_index], image=photo
                        )
                        self.canvas.itemconfigure(
                            self.lazy_page_placeholders[page_index], state='hidden'
                        )
                    except tk.TclError:
                        self.lazy_failed_pages.add(page_index)

                self.lazy_page_request_ids.pop(page_index, None)
                self.lazy_page_request_priorities.pop(page_index, None)

        pending_pages = any(
            page_index in self.lazy_page_request_ids
            for page_index in self.lazy_needed_pages
        )
        if pending_pages:
            self.lazy_render_poll_job = self.root.after(
                15, self.poll_lazy_render_results
            )

    def schedule_zoom_render(self):
        """合并连续的 +/- 按键，只重绘最后一次缩放比例。"""
        self.cancel_pending_zoom_render()
        self.zoom_render_job = self.root.after(80, self.apply_zoom_render)

    def apply_zoom_render(self):
        self.zoom_render_job = None
        self.show_image()
        if hasattr(self, 'current_file_path'):
            self.save_image_config(self.current_file_path)

    def zoom_in(self, event):
        if not self.current_image:
            return
        self.scale += 0.1
        self.schedule_zoom_render()

    def zoom_out(self, event):
        if not self.current_image:
            return
        self.scale = max(0.1, self.scale - 0.1)
        self.schedule_zoom_render()
    
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
        self.search_stop_event.set()
        zoom_was_pending = self.zoom_render_job is not None
        self.cancel_pending_zoom_render()
        self.lazy_render_stop_event.set()
        self.render_generation += 1
        for job_name in ('lazy_render_poll_job', 'lazy_view_request_job',
                         'deferred_render_job', 'resize_timer'):
            job = getattr(self, job_name, None)
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
                setattr(self, job_name, None)
        if zoom_was_pending and hasattr(self, 'current_file_path'):
            self.save_image_config(self.current_file_path)
        if self.search_size_save_job is not None:
            try:
                self.root.after_cancel(self.search_size_save_job)
            except tk.TclError:
                pass
            self.search_size_save_job = None
        self.save_search_window_geometry()
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
            self.schedule_visible_page_request()
    
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
