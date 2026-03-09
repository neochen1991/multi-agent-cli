import React from 'react';
void React;

export const PageHeader: React.FC<{
  title: string;
  desc: string;
  actions?: React.ReactNode;
}> = ({ title, desc, actions }) => (
  <section className="page-header">
    <div>
      <h2>{title}</h2>
      <p>{desc}</p>
    </div>
    <div className="header-actions">{actions}</div>
  </section>
);

export const Panel: React.FC<{
  title: string;
  subtitle?: string;
  extra?: React.ReactNode;
  children: React.ReactNode;
}> = ({ title, subtitle, extra, children }) => (
  <div className="panel">
    <div className="panel-head">
      <div>
        <h3 className="panel-title">{title}</h3>
        {subtitle ? <div className="panel-subtitle">{subtitle}</div> : null}
      </div>
      {extra}
    </div>
    {children}
  </div>
);

export const Badge: React.FC<{ tone?: 'brand' | 'teal' | 'amber' | 'red'; children: React.ReactNode }> = ({ tone = 'brand', children }) => (
  <span className={`badge ${tone}`}>{children}</span>
);
