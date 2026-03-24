import {
  AlertTriangle,
  CheckCircle,
  Leaf,
  Bell,
  Lightbulb,
  Rocket,
  Navigation,
  Plus,
  Minus,
  Locate,
  Route,
  BatteryCharging,
  Bot,
  AlertOctagon,
  PlayCircle,
  PauseCircle,
  LayoutDashboard,
  Sprout,
  BellRing,
  Radio,
  Archive,
  Droplets,
  Blinds,
  Wind,
  FlaskConical,
  Router,
  Circle,
  LucideIcon
} from 'lucide-react';

type AppIconProps = {
  name: string
  className?: string
  filled?: boolean
}

const iconMap: Record<string, LucideIcon> = {
  'warning': AlertTriangle,
  'task_alt': CheckCircle,
  'eco': Leaf,
  'notifications': Bell,
  'lightbulb': Lightbulb,
  'rocket_launch': Rocket,
  'navigation': Navigation,
  'add': Plus,
  'remove': Minus,
  'my_location': Locate,
  'route': Route,
  'battery_charging_80': BatteryCharging,
  'precision_manufacturing': Bot,
  'emergency_home': AlertOctagon,
  'play_circle': PlayCircle,
  'pause_circle': PauseCircle,
  'dashboard': LayoutDashboard,
  'potted_plant': Sprout,
  'notifications_active': BellRing,
  'sensors': Radio,
  'inventory_2': Archive,
  'water_drop': Droplets,
  'curtains': Blinds,
  'air': Wind,
  'science': FlaskConical,
  'router': Router
};

export function AppIcon({
  name,
  className,
  filled = false,
}: AppIconProps) {
  const IconComponent = iconMap[name] || Circle;

  // lucide-react properties
  // filled usually means fill="currentColor" if requested, otherwise "none"
  const fillProps = filled ? { fill: "currentColor" } : {};

  return (
    <IconComponent 
      className={className} 
      size={24} 
      {...fillProps} 
    />
  )
}

