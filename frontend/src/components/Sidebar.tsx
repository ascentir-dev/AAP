import { Icon } from "@blueprintjs/core";
import type { IconName } from "@blueprintjs/icons";

type Page =
  | "dashboard"
  | "leads"
  | "pipeline"
  | "costs"
  | "sms-dashboard"
  | "sms-conversations"
  | "video-analytics"
  | "testing-dashboard"
  | "playbook";

interface NavItemProps {
  icon: IconName;
  label: string;
  page: Page;
  active: boolean;
  onClick: (page: Page) => void;
}

function NavItem({ icon, label, page, active, onClick }: NavItemProps) {
  return (
    <button
      className={`nav-item${active ? " active" : ""}`}
      onClick={() => onClick(page)}
    >
      <Icon icon={icon} size={14} />
      {label}
    </button>
  );
}

interface SidebarProps {
  current: Page;
  onChange: (page: Page) => void;
}

export function Sidebar({ current, onChange }: SidebarProps) {
  return (
    <div className="sidebar">
      <div className="sidebar-logo">
        <div className="sidebar-logo-mark">A</div>
        <div className="sidebar-logo-text">
          <span className="sidebar-brand">Ascentir</span>
          <span className="sidebar-sub">Outreach OS</span>
        </div>
      </div>

      <nav className="sidebar-nav">
        <div className="nav-section-header">Email Outreach</div>
        <NavItem
          icon="dashboard"
          label="Dashboard"
          page="dashboard"
          active={current === "dashboard"}
          onClick={onChange}
        />
        <NavItem
          icon="people"
          label="Leads"
          page="leads"
          active={current === "leads"}
          onClick={onChange}
        />

        <div className="nav-section-header" style={{ marginTop: 12 }}>
          Operations
        </div>
        <NavItem
          icon="upload"
          label="Pipeline"
          page="pipeline"
          active={current === "pipeline"}
          onClick={onChange}
        />
        <NavItem
          icon="dollar"
          label="Cost Tracker"
          page="costs"
          active={current === "costs"}
          onClick={onChange}
        />

        <div className="nav-section-header" style={{ marginTop: 12 }}>
          SMS Outreach
        </div>
        <NavItem
          icon="mobile-phone"
          label="SMS Dashboard"
          page="sms-dashboard"
          active={current === "sms-dashboard"}
          onClick={onChange}
        />
        <NavItem
          icon="chat"
          label="Conversations"
          page="sms-conversations"
          active={current === "sms-conversations"}
          onClick={onChange}
        />

        <div className="nav-section-header" style={{ marginTop: 12 }}>
          Video
        </div>
        <NavItem
          icon="video"
          label="Script A/B"
          page="video-analytics"
          active={current === "video-analytics"}
          onClick={onChange}
        />
        <NavItem
          icon="lab-test"
          label="Testing Framework"
          page="testing-dashboard"
          active={current === "testing-dashboard"}
          onClick={onChange}
        />

        <div className="nav-section-header" style={{ marginTop: 12 }}>
          Configuration
        </div>
        <NavItem
          icon="book"
          label="Playbook"
          page="playbook"
          active={current === "playbook"}
          onClick={onChange}
        />
      </nav>
    </div>
  );
}

export type { Page };
