"""FSM states for post creation."""
from aiogram.fsm.state import State, StatesGroup


class PostCreation(StatesGroup):
    """States for creating a new post."""

    waiting_topic_angle = State()
    waiting_audience = State()
    waiting_key_takeaway = State()
    waiting_extra_points = State()
    confirm = State()


class ContentPlanFlow(StatesGroup):
    """States for content plan creation + feedback loop."""

    waiting_feedback = State()  # free text feedback or /approve


class AutopostFlow(StatesGroup):
    """States for autopost pipeline execution."""

    running = State()  # pipeline is running, can be cancelled
