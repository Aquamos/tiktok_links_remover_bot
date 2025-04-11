import re
import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "7646304556:AAGVgl9oZk8r-mMGPY_6t2Ttr1MBczVeWIo"
BOT_USERNAME = "tiktok_links_remover_bot"

deletion_settings = {}
scheduled_deletions = {}

TIKTOK_REGEX = re.compile(r'https?://(?:www\.|vm\.|vt\.)?tiktok\.com/[^\s]+')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_type = update.effective_chat.type
    
    if chat_type == "private":
        keyboard = [
            [InlineKeyboardButton("Set Auto-Delete Timer", callback_data="set_timer")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Welcome to TikTok Link Handler Bot!\n\n"
            "I can help you manage TikTok links in your chat:\n"
            "- Automatically delete TikTok links after a custom time period\n\n"
            "Add me to a group and make me an admin with 'Delete Messages' permission to get started.",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "TikTok Link Handler Bot is now active in this group!\n\n"
            "Available commands:\n"
            "/set_timer [seconds] - Set time to auto-delete TikTok links\n"
            "/disable - Turn off auto-deletion\n"
            "/help - Show all commands\n\n"
            "Make sure I have 'Delete Messages' permission as an admin."
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    if query.data == "set_timer":
        await query.edit_message_text(
            "Please send the number of seconds to wait before deleting TikTok links.\n"
            "For example, send '60' to delete links after 1 minute."
        )
        context.user_data["waiting_for_timer"] = True
    elif query.data.startswith("confirm_delete_"):
        try:
            seconds = int(query.data.split("_")[2])
            await query.edit_message_text(
                f"TikTok links will now be automatically deleted after {seconds} seconds in this chat."
            )
            deletion_settings[query.message.chat_id] = seconds
        except (ValueError, IndexError):
            await query.edit_message_text("Invalid selection. Please try again.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
        
    if context.user_data.get("waiting_for_timer", False) and update.effective_chat.type == "private":
        try:
            seconds = int(update.message.text.strip())
            if seconds <= 0:
                await update.message.reply_text("Please enter a positive number of seconds.")
                return
                
            keyboard = [
                [InlineKeyboardButton(f"Confirm: {seconds} seconds", callback_data=f"confirm_delete_{seconds}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"Are you sure you want to set auto-delete timer to {seconds} seconds?",
                reply_markup=reply_markup
            )
            
            context.user_data["waiting_for_timer"] = False
            return
        except ValueError:
            await update.message.reply_text("Please enter a valid number of seconds.")
            return
    
    if TIKTOK_REGEX.search(update.message.text):
        chat_id = update.effective_chat.id
        message_id = update.message.message_id
        
        try:
            chat_member = await context.bot.get_chat_member(chat_id, context.bot.id)
            can_delete = getattr(chat_member, "can_delete_messages", False)
            
            if chat_id in deletion_settings:
                delete_after = deletion_settings[chat_id]
                
                if not can_delete:
                    if update.effective_chat.type != "private":
                        await update.message.reply_text(
                            "TikTok link detected, but I don't have permission to delete messages. "
                            "Please make me an admin with 'Delete Messages' permission."
                        )
                    return
                    
                notification = None
                if update.effective_chat.type != "private":
                    notification = await update.message.reply_text(
                        f"TikTok link detected. It will be deleted in {delete_after} seconds."
                    )
                
                delete_time = datetime.now() + timedelta(seconds=delete_after)
                
                context.job_queue.run_once(
                    delete_message_job,
                    delete_after,
                    data={
                        'chat_id': chat_id,
                        'message_id': message_id
                    }
                )
                
                if notification:
                    context.job_queue.run_once(
                        delete_message_job,
                        delete_after,
                        data={
                            'chat_id': chat_id,
                            'message_id': notification.message_id
                        }
                    )
            elif update.effective_chat.type != "private":
                await update.message.reply_text(
                    "TikTok link detected. Auto-deletion is not enabled for this chat.\n"
                    "An admin can enable it with the command:\n"
                    "/set_timer [seconds]"
                )
        except Exception as e:
            logger.error(f"Error processing TikTok link: {e}")

async def delete_message_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    data = job.data
    
    try:
        await context.bot.delete_message(
            chat_id=data['chat_id'],
            message_id=data['message_id']
        )
        logger.info(f"Deleted message {data['message_id']} in chat {data['chat_id']}")
    except Exception as e:
        logger.error(f"Failed to delete message: {e}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_type = update.effective_chat.type
    
    if chat_type == "private":
        await update.message.reply_text(
            "TikTok Link Handler Bot Commands:\n\n"
            "/start - Start the bot and show main menu\n"
            "/set_timer [seconds] - Set auto-delete timer (e.g., /set_timer 60)\n"
            "/disable - Disable auto-deletion of TikTok links\n"
            "/help - Show this help message\n\n"
            "To use me in a group, add me to the group and make me an admin with 'Delete Messages' permission."
        )
    else:
        await update.message.reply_text(
            "TikTok Link Handler Bot Commands for Groups:\n\n"
            "/set_timer [seconds] - Set auto-delete timer (e.g., /set_timer 60)\n"
            "/disable - Disable auto-deletion of TikTok links\n"
            "/help - Show this help message\n\n"
            "Important: Make sure I have 'Delete Messages' permission as an admin.\n"
            f"To configure advanced settings, chat with me privately: @{BOT_USERNAME}"
        )

async def set_timer_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "Please specify the number of seconds to wait before deleting TikTok links.\n"
            "Example: /set_timer 60"
        )
        return
    
    try:
        seconds = int(context.args[0])
        if seconds <= 0:
            await update.message.reply_text("Please enter a positive number of seconds.")
            return
            
        chat_id = update.effective_chat.id
        deletion_settings[chat_id] = seconds
        
        await update.message.reply_text(
            f"TikTok links will now be automatically deleted after {seconds} seconds in this chat."
        )
    except ValueError:
        await update.message.reply_text("Please enter a valid number of seconds.")

async def disable_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    
    if chat_id in deletion_settings:
        del deletion_settings[chat_id]
        await update.message.reply_text("Auto-deletion of TikTok links has been disabled for this chat.")
    else:
        await update.message.reply_text("Auto-deletion was not enabled for this chat.")

async def group_chat_joined(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Thanks for adding me to this group!\n\n"
        "I can automatically delete TikTok links after a specific time period.\n\n"
        "To get started:\n"
        "1. Make me an admin with 'Delete Messages' permission\n"
        "2. Set auto-delete timer with: /set_timer [seconds]\n\n"
        "For help, type /help"
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Update {update} caused error: {context.error}")

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("set_timer", "Set auto-delete timer for TikTok links"),
        BotCommand("disable", "Disable auto-deletion"),
        BotCommand("help", "Show available commands")
    ]

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("set_timer", set_timer_command))
    application.add_handler(CommandHandler("disable", disable_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, group_chat_joined))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    application.bot.set_my_commands(commands)
    application.run_polling()

if __name__ == "__main__":
    main()
