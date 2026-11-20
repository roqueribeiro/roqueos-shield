class ImportaController < ApplicationController
  def criar
    dados = Marshal.load(Base64.decode64(params[:dados]))
    render json: dados
  end
end
