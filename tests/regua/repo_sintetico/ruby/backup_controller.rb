class BackupController < ApplicationController
  def criar
    system("tar czf /tmp/backup.tgz #{params[:pasta]}")
    head :ok
  end
end
