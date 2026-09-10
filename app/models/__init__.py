from app.models.role import Role
from app.models.user import User, RoleUser, UserDetail, UserParent
from app.models.organization import Organization, OrganizationMember
from app.models.menu import Menu, MenuRole
from app.models.country import Country
from app.models.parameter import Parameter, ParameterDetail
from app.models.muscle_group import MuscleGroup, MuscleGroupClient
from app.models.training import Training, TrainingClient
from app.models.routine import Routine, RoutineDay, RoutineDayDetail, RoutineBlock
from app.models.client_target import ClientTarget
from app.models.event_user import EventUser
from app.models.type_event import TypeEvent
from app.models.template_notes import TemplateNote
from app.models.note_user import NoteUser
from app.models.progress_day import ProgressDay
from app.models.nutrition.type_food import TypeFood
from app.models.nutrition.group_food import GroupFood
from app.models.nutrition.aliment import Aliment, AlimentDescription
from app.models.nutrition.diet import Diet, DietDetail, DietFood, DietFoodAliment
from app.models.nutrition.recipe import Recipe, RecipeDetail
from app.models.nutrition.client_aliment import ClientAliment
from app.models.form import FormTemplate, FormTemplateField, FormAssignment, FormResponse
from app.models.checkin import WeeklyCheckin
from app.models.session_log import WorkoutSession, WorkoutSessionExercise, WorkoutSessionSet
from app.models.client_task import ClientTask
from app.models.app_setting import AppSetting
from app.models.program import Program, ProgramPhase, ProgramClient
from app.models.weekly_menu import WeeklyMenu, WeeklyMenuDay
from app.models.client_menu import ClientMenu
from app.models.nutrition_day import ClientNutritionDay
from app.models.client_exercise import ClientExercise
from app.models.calendar_task import CalendarTask
# Modelos que faltaban en el registro: sin ellos Base.metadata queda incompleta
# (en las pruebas no se creaban sus tablas y el borrado de una dieta fallaba).
from app.models.plan import PlanDelivery
from app.models.chat import ChatConversation, ChatParticipant, ChatMessage
from app.models.contract import Contract, ContractTemplate
from app.models.document import Document
from app.models.team_member import TeamMember
from app.models.support import SupportTicket, SupportTicketMessage, PlatformAnnouncement
from app.models.platform_setting import PlatformSetting
from app.models.subscription_plan import SubscriptionPlan
