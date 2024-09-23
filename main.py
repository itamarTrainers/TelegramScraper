import sys
import os
import json  # Import json module to handle JSON writing
import configparser
import asyncio
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton,
    QLineEdit, QLabel, QFileDialog, QMessageBox
)
from PySide6.QtCore import QThread, Signal, Slot
from telethon.sync import TelegramClient


class ScraperThread(QThread):
    progress = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, api_id, api_hash, phone_number, chat_username, output_file, stop_flag):
        super().__init__()
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone_number = phone_number
        self.chat_username = chat_username
        self.output_file = output_file
        self.stop_flag = stop_flag

    def run(self):
        try:
            asyncio.run(self.scrape_all_messages())
        except Exception as e:
            self.error.emit(f"An error occurred: {str(e)}")

    async def scrape_all_messages(self):
        client = TelegramClient('scraper_session', self.api_id, self.api_hash)

        await client.start(self.phone_number)

        try:
            chat = await client.get_entity(self.chat_username)

            # Ensure the file is created if it doesn't exist
            if not os.path.exists(self.output_file):
                open(self.output_file, 'w').close()

            # Collect messages as a list of dictionaries
            messages = []

            offset_id = 0  # Start from the first message
            limit = 100    # Fetch messages in chunks of 100

            while not self.stop_flag.is_set():
                history = await client.get_messages(chat, limit=limit, offset_id=offset_id)

                if not history:
                    break

                for message in history:
                    message_url = f"https://t.me/{chat.username}/{message.id}" if chat.username else "No URL"

                    message_dict = {
                        "message_id": message.id,
                        "date": str(message.date),
                        "message_url": message_url,
                        "text": message.text or "",
                    }

                    if message.photo:
                        image_url = f"https://t.me/{chat.username}/{message.id}"
                        message_dict["image_url"] = image_url

                    messages.append(message_dict)

                offset_id = history[-1].id

                # Emit progress update
                self.progress.emit(f"Scraping... Collected {offset_id} messages")

            # Write collected messages to a JSON file
            with open(self.output_file, 'w', encoding='utf-8') as file:
                json.dump(messages, file, ensure_ascii=False, indent=4)

            self.finished.emit(f"Scraping completed! Messages saved to {self.output_file}")

        except Exception as e:
            self.error.emit(f"An error occurred during scraping: {str(e)}")

        finally:
            await client.disconnect()


class TelegramScraperGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.scraper_thread = None
        self.stop_flag = asyncio.Event()

    def init_ui(self):
        self.setWindowTitle("Telegram Scraper")
        self.setGeometry(300, 300, 400, 300)

        widget = QWidget()
        layout = QVBoxLayout()

        # Input for chat username
        self.chat_username_input = QLineEdit(self)
        self.chat_username_input.setPlaceholderText("Enter the chat username (e.g., @example_channel)")
        layout.addWidget(QLabel("Chat Username:"))
        layout.addWidget(self.chat_username_input)

        # Input for output file
        self.output_file_input = QLineEdit(self)
        self.output_file_input.setPlaceholderText("Enter the output file name (e.g., messages.json)")
        layout.addWidget(QLabel("Output File:"))
        layout.addWidget(self.output_file_input)

        # Browse button to select the output file
        self.browse_button = QPushButton("Browse...", self)
        self.browse_button.clicked.connect(self.select_output_file)
        layout.addWidget(self.browse_button)

        # Scrape button
        self.scrape_button = QPushButton("Scrape Messages", self)
        self.scrape_button.clicked.connect(self.start_scraping)
        layout.addWidget(self.scrape_button)

        # Cancel button
        self.cancel_button = QPushButton("Cancel Scraping", self)
        self.cancel_button.clicked.connect(self.stop_scraping)
        layout.addWidget(self.cancel_button)

        # Status label to show progress
        self.status_label = QLabel("", self)
        layout.addWidget(self.status_label)

        widget.setLayout(layout)
        self.setCentralWidget(widget)

    def select_output_file(self):
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getSaveFileName(
            self, "Save Output File", "", "JSON Files (*.json);;All Files (*)", options=options
        )
        if file_name:
            self.output_file_input.setText(file_name)

    def start_scraping(self):
        chat_username = self.chat_username_input.text().strip()
        output_file = self.output_file_input.text().strip()

        if not chat_username or not output_file:
            QMessageBox.warning(self, "Input Error", "Please enter both the chat username and output file path.")
            return

        # Reset stop flag and start scraping
        self.stop_flag.clear()
        self.status_label.setText("Scraping started...")
        self.scrape_button.setEnabled(False)
        self.cancel_button.setEnabled(True)

        # Load configuration from config.ini
        config = configparser.ConfigParser()
        config.read('config.ini')

        api_id = config['telegram']['api_id']
        api_hash = config['telegram']['api_hash']
        phone_number = config['telegram']['phone_number']

        # Start the scraper thread
        self.scraper_thread = ScraperThread(api_id, api_hash, phone_number, chat_username, output_file, self.stop_flag)
        self.scraper_thread.progress.connect(self.update_progress)
        self.scraper_thread.finished.connect(self.scraping_finished)
        self.scraper_thread.error.connect(self.handle_error)
        self.scraper_thread.start()

    def stop_scraping(self):
        self.stop_flag.set()
        self.status_label.setText("Scraping stopped.")
        self.scrape_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    @Slot(str)
    def update_progress(self, message):
        self.status_label.setText(message)

    @Slot(str)
    def scraping_finished(self, message):
        self.status_label.setText(message)
        self.scrape_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    @Slot(str)
    def handle_error(self, error_message):
        self.status_label.setText(error_message)
        self.scrape_button.setEnabled(True)
        self.cancel_button.setEnabled(False)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = TelegramScraperGUI()
    window.show()
    sys.exit(app.exec())
