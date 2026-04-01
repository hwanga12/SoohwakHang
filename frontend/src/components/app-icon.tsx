/*
 * 이 컴포넌트는 프론트엔드 화면에서 앱 아이콘 역할을 맡는다.
 */
import {
  AlertTriangle,
  CheckCircle,
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
  X,
  Circle,
  LucideIcon,
  LucideProps
} from 'lucide-react';

/**
 * furniture leaf 화면 조각을 렌더링하는 컴포넌트다.
 */
const FurnitureLeaf = ({ size = 24, fill = "none", ...props }: LucideProps) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill={fill}
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    {...props}
  >
    <path d="M12 22C12 22 20 18 20 10C20 5.58172 16.4183 2 12 2C7.58172 2 4 5.58172 4 10C4 18 12 22 12 22Z" />
    <circle cx="17" cy="6" r="3" fill="white" stroke="none" />
    <path d="M12 22v-4" />
  </svg>
);

type AppIconProps = {
  name: string
  className?: string
  style?: React.CSSProperties
  filled?: boolean
}

const iconMap: Record<string, LucideIcon> = {
  'warning': AlertTriangle,
  'task_alt': CheckCircle,
  'eco': FurnitureLeaf as LucideIcon,
  'notifications': Bell,
  'lightbulb': Lightbulb,
  'rocket_launch': Rocket,
  'navigation': Navigation,
  'add': Plus,
  'remove': Minus,
  'close': X,
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

/**
 * APP 아이콘 화면 조각을 렌더링하는 컴포넌트다.
 */
export function AppIcon({
  name,
  className,
  style,
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
      style={style}
      {...fillProps} 
    />
  )
}
