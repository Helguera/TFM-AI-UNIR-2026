"""
Telegram Bot Service - Send notifications and handle commands
"""

import asyncio
import threading
from pathlib import Path
from typing import Optional, Dict, Callable
from datetime import datetime
import traceback
from concurrent.futures import TimeoutError

from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from telegram.ext import Application, CommandHandler, ContextTypes


class TelegramNotifier:
    """
    Telegram bot for sending notifications and responding to commands.
    """

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id

        # Bot para enviar mensajes (independiente de Application)
        self.bot = Bot(token=token)

        self._application: Optional[Application] = None
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._get_cameras_status: Optional[Callable] = None

    def set_cameras_status_callback(self, callback: Callable):
        """Set callback to get cameras status."""
        self._get_cameras_status = callback

    async def send_alert(
        self,
        camera_name: str,
        event_type: str,
        confidence: float,
        image_path: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> bool:
        """Send alert notification with optional image."""
        try:
            timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

            # MarkdownV2: escapar todo lo dinámico
            cam = escape_markdown(camera_name or "", version=2)
            evt = escape_markdown(event_type or "", version=2)
            conf = escape_markdown(f"{confidence:.1%}", version=2)  # puede contener '.'
            ts = escape_markdown(timestamp, version=2)
            det = escape_markdown(detail or "", version=2)

            message = (
                "🚨 *ALERTA DE INTRUSIÓN*\n\n"
                f"📹 *Cámara:* {cam}\n"
                f"⚠️ *Tipo:* {evt}\n"
                f"📊 *Confianza:* {conf}\n"
                f"🕐 *Hora:* {ts}\n"
            )
            if detail:
                message += f"📝 *Detalle:* {det}\n"

            if image_path and Path(image_path).exists():
                with open(image_path, "rb") as photo:
                    await self.bot.send_photo(
                        chat_id=self.chat_id,
                        photo=photo,
                        caption=message,
                        parse_mode=ParseMode.MARKDOWN_V2,
                    )
            else:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )

            return True

        except Exception as e:
            print(f"[Telegram] Error sending alert: {e}")
            traceback.print_exc()
            return False

    def send_alert_sync(
        self,
        camera_name: str,
        event_type: str,
        confidence: float,
        image_path: Optional[str] = None,
        detail: Optional[str] = None,
        timeout_s: float = 10.0,
    ) -> bool:
        """
        Synchronous wrapper for send_alert.

        Importante: NO crea un event loop nuevo por llamada.
        Si el bot está corriendo en su hilo con loop activo, agenda ahí la corrutina.
        """
        try:
            coro = self.send_alert(camera_name, event_type, confidence, image_path, detail)

            if self._loop and self._loop.is_running():
                fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
                try:
                    return fut.result(timeout=timeout_s)
                except TimeoutError:
                    print("[Telegram] Error in sync send: timeout waiting for send_alert")
                    return False
            else:
                # Fallback (por si llamas antes de arrancar polling)
                return asyncio.run(coro)

        except Exception as e:
            print(f"[Telegram] Error in sync send: {e}")
            traceback.print_exc()
            return False

    async def send_message(self, text: str) -> bool:
        """Send a simple text message (seguro en MarkdownV2)."""
        try:
            safe = escape_markdown(text or "", version=2)
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=safe,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return True
        except Exception as e:
            print(f"[Telegram] Error sending message: {e}")
            traceback.print_exc()
            return False

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        await update.message.reply_text(
            "🎯 *SurveillanceHQ Bot*\n\n"
            "Recibirás notificaciones de alertas automáticamente\.\n\n"
            "*Comandos disponibles:*\n"
            "/status \- Ver estado de las cámaras\n"
            "/help \- Mostrar ayuda",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command - show cameras status."""
        if not self._get_cameras_status:
            await update.message.reply_text("⚠️ Sistema no disponible")
            return

        try:
            statuses = self._get_cameras_status() or []

            if not statuses:
                await update.message.reply_text(
                    "📹 *Estado de Cámaras*\n\n"
                    "No hay cámaras configuradas\.",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                return

            message = "📹 *Estado de Cámaras*\n\n"

            for cam in statuses:
                status_icon = "🟢" if cam.get("is_running") else "🔴"
                name = escape_markdown(str(cam.get("name", "")), version=2)
                estado = "Activa" if cam.get("is_running") else "Detenida"
                estado = escape_markdown(estado, version=2)

                message += (
                    f"{status_icon} *{name}*\n"
                    f"   Estado: {estado}\n"
                )

                fps = cam.get("fps")
                if cam.get("is_running") and fps is not None:
                    fps_txt = escape_markdown(f"{float(fps):.1f}", version=2)
                    message += f"   FPS: {fps_txt}\n"

                message += "\n"

            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        await update.message.reply_text(
            "🎯 *SurveillanceHQ \- Ayuda*\n\n"
            "*Comandos:*\n"
            "/start \- Iniciar el bot\n"
            "/status \- Ver estado de las cámaras\n"
            "/help \- Mostrar esta ayuda\n\n"
            "*Notificaciones:*\n"
            "Recibirás alertas automáticas cuando se detecte una intrusión, "
            "incluyendo la imagen capturada y detalles del evento\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    def _run_polling(self):
        """Run the bot polling in a separate thread."""

        async def run():
            try:
                self._application = Application.builder().token(self.token).build()

                # Handlers
                self._application.add_handler(CommandHandler("start", self._cmd_start))
                self._application.add_handler(CommandHandler("status", self._cmd_status))
                self._application.add_handler(CommandHandler("help", self._cmd_help))

                # Start
                await self._application.initialize()
                await self._application.start()
                await self._application.updater.start_polling(drop_pending_updates=True)

                self._running = True
                print("[Telegram] Bot started polling")

                while self._running:
                    await asyncio.sleep(1)

            except Exception as e:
                print(f"[Telegram] Polling crashed: {e}")
                traceback.print_exc()

            finally:
                # Cleanup seguro
                try:
                    if self._application and self._application.updater:
                        await self._application.updater.stop()
                except Exception:
                    pass
                try:
                    if self._application:
                        await self._application.stop()
                except Exception:
                    pass
                try:
                    if self._application:
                        await self._application.shutdown()
                except Exception:
                    pass

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(run())
        finally:
            self._loop.close()

    def start_polling(self):
        """Start the bot in a background thread."""
        if self._thread and self._thread.is_alive():
            return

        self._thread = threading.Thread(target=self._run_polling, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the bot."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)


class TelegramManager:
    """
    Singleton manager for Telegram bot.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._notifier: Optional[TelegramNotifier] = None
        self._enabled = False
        self._get_cameras_status: Optional[Callable] = None
        self._initialized = True

    def configure(self, token: str, chat_id: str, enabled: bool = True):
        """Configure and start the Telegram bot."""
        self.stop()

        if not token or not chat_id:
            print("[Telegram] Missing token or chat_id")
            return False

        try:
            self._notifier = TelegramNotifier(token, chat_id)
            if self._get_cameras_status:
                self._notifier.set_cameras_status_callback(self._get_cameras_status)

            self._enabled = enabled

            if enabled:
                self._notifier.start_polling()

            return True
        except Exception as e:
            print(f"[Telegram] Error configuring bot: {e}")
            traceback.print_exc()
            return False

    def set_cameras_status_callback(self, callback: Callable):
        """Set callback to get cameras status."""
        self._get_cameras_status = callback
        if self._notifier:
            self._notifier.set_cameras_status_callback(callback)

    def send_alert(
        self,
        camera_name: str,
        event_type: str,
        confidence: float,
        image_path: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> bool:
        """Send alert notification."""
        if not self._enabled or not self._notifier:
            return False

        return self._notifier.send_alert_sync(
            camera_name=camera_name,
            event_type=event_type,
            confidence=confidence,
            image_path=image_path,
            detail=detail,
        )

    def is_configured(self) -> bool:
        """Check if bot is configured."""
        return self._notifier is not None

    def is_enabled(self) -> bool:
        """Check if notifications are enabled."""
        return self._enabled

    def stop(self):
        """Stop the bot."""
        if self._notifier:
            self._notifier.stop()
            self._notifier = None
        self._enabled = False


# Global instance
telegram_manager = TelegramManager()


async def test_connection(token: str, chat_id: str) -> Dict:
    """Test Telegram connection with given credentials."""
    try:
        bot = Bot(token=token)
        await bot.send_message(
            chat_id=chat_id,
            text="✅ *SurveillanceHQ*\n\nConexión establecida correctamente\!",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return {"success": True, "message": "Conexión exitosa"}
    except Exception as e:
        return {"success": False, "message": str(e)}
